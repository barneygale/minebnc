import collections
import os.path

from twisted.internet import reactor, defer
from twisted.internet.protocol import ReconnectingClientFactory

from quarry.types.chunk import BlockArray, LightArray
from quarry.net.auth import Profile, OfflineProfile
from quarry.net.client import ClientFactory, ClientProtocol
from quarry.net.server import ServerFactory, ServerProtocol

from config import *


# Globals ---------------------------------------------------------------------

downstream = None
upstream = None


# Server ----------------------------------------------------------------------


def f2b(n):
    return int((n % 360.0) * 256.0 / 360.0)


def b2f(n):
    return n * 360.0 / 256.0


class Downstream(ServerProtocol):
    def setup(self):
        global downstream
        downstream = self

    def connection_made(self):
        if whitelist and self.remote_addr.host not in whitelist:
            self.close()
        else:
            super(Downstream, self).connection_made()

    def packet_received(self, buff, name):
        if upstream.forwarding:
            buff.save()
            upstream.send_packet(name, buff.read())
            buff.restore()
        super(Downstream, self).packet_received(buff, name)

    def player_joined(self):
        super(Downstream, self).player_joined()
        if upstream:
            upstream.downstream_player_joined()

    def player_left(self):
        if upstream:
            upstream.downstream_player_left()

    def packet_player(self, buff):
        upstream.game['player']['on_ground'] = buff.unpack('?')

    def packet_player_position(self, buff):
        upstream.game['player']['x'] = buff.unpack('d')
        upstream.game['player']['y'] = buff.unpack('d')
        upstream.game['player']['z'] = buff.unpack('d')
        upstream.game['player']['on_ground'] = buff.unpack('?')

    def packet_player_look(self, buff):
        upstream.game['player']['yaw'] = buff.unpack('f')
        upstream.game['player']['pitch'] = buff.unpack('f')
        upstream.game['player']['on_ground'] = buff.unpack('?')

    def packet_player_position_and_look(self, buff):
        upstream.game['player']['x'] = buff.unpack('d')
        upstream.game['player']['y'] = buff.unpack('d')
        upstream.game['player']['z'] = buff.unpack('d')
        upstream.game['player']['yaw'] = buff.unpack('f')
        upstream.game['player']['pitch'] = buff.unpack('f')
        upstream.game['player']['on_ground'] = buff.unpack('?')

    def packet_vehicle_move(self, buff):
        player = upstream.game['player']
        vehicle = upstream.game['entities'][player['vehicle']]

        player['x'] = vehicle['x'] = buff.unpack('d')
        player['y'] = vehicle['y'] = buff.unpack('d')
        player['z'] = vehicle['z'] = buff.unpack('d')
        player['yaw'] = vehicle['yaw'] = buff.unpack('f')
        player['pitch'] = vehicle['pitch'] = buff.unpack('f')

    def packet_entity_action(self, buff):
        entity_id = buff.unpack_varint()
        action = buff.unpack_varint()
        jump_boost = buff.unpack_varint()

        if action == 0:
            upstream.game['player']['actions']['sneaking'] = True
        elif action == 1:
            upstream.game['player']['actions']['sneaking'] = False
        elif action == 2:
            upstream.game['player']['bed'] = None
        elif action == 3:
            upstream.game['player']['actions']['sprinting'] = True
        elif action == 4:
            upstream.game['player']['actions']['sprinting'] = False
        elif action == 5:
            upstream.game['player']['actions']['horse_jumping'] = True
        elif action == 6:
            upstream.game['player']['actions']['horse_jumping'] = False
        elif action == 7:
            pass  # TODO: horse inventory
        elif action == 8:
            pass  # TODO: elytra

    def packet_held_item_change(self, buff):
        upstream.game['held_item'] = buff.unpack('h')

    def packet_player_abilities(self, buff):
        flags = buff.unpack('B')
        upstream.game['abilities']['invulnerable']  = bool(flags & 1)
        upstream.game['abilities']['flying']        = bool(flags & 2)
        upstream.game['abilities']['allow_flying']  = bool(flags & 4)
        upstream.game['abilities']['creative_mode'] = bool(flags & 8)
        upstream.game['abilities']['flying_speed']  = buff.unpack('f')
        upstream.game['abilities']['fov_modifier']  = buff.unpack('f')


class DownstreamFactory(ServerFactory):
    protocol = Downstream
    max_players = 1

    online_mode = online_mode
    motd = motd
    force_protocol_version = protocol_version
    log_level = log_level


# Client ----------------------------------------------------------------------

class Upstream(ClientProtocol):
    spawned = False
    forwarding = False
    game = None

    # Utilities ---------------------------------------------------------------

    def start_forwarding(self):
        self.logger.info("Starting forwarding")
        self.forwarding = True
        self.ticker.stop()

    def stop_forwarding(self):
        self.logger.info("Stopped forwarding")
        self.forwarding = False
        self.ticker.start()

    def set_block(self, x, y, z, block_id):
        cx, bx = divmod(x, 16)
        cy, by = divmod(y, 16)
        cz, bz = divmod(z, 16)

        chunk = self.game['chunks'].get((cx, cz))
        if chunk:
            chunk['sections'][cy][0][by*256 + bz*16 + bx] = block_id

        # TODO: adjust lighting

    # Callbacks ---------------------------------------------------------------

    def setup(self):
        self.game = {
            'abilities': {},
            'chunks': {},
            'inventory': [{'id': -1} for _ in range(46)],
            'world_border': {},
            'entities':  collections.defaultdict(lambda: {
                "type": "unknown",
                "x": 0,
                "y": 0,
                "z": 0,
            }),
            'raining': False,
            'resource_pack': {'url': '', 'hash': ''},
            'chat_messages': [],
            'held_item': 0,
            'recipes': set(),
            'players': {},
            'boss_bars': {},
            'channels': set(),
        }

    def connection_made(self):
        super(Upstream, self).connection_made()
        global upstream
        upstream = self

    def connection_lost(self, reason=None):
        super(Upstream, self).connection_lost(reason)
        global upstream
        upstream = None

    def downstream_player_joined(self):
        self.attach()

    def downstream_player_left(self):
        self.detach()

    def player_spawned(self):
        self.spawned = True

        self.ticker.add_loop(1, self.update_player_inc)
        self.ticker.add_loop(20, self.update_player_full)

    # Tasks -------------------------------------------------------------------

    def update_player_inc(self):
        player = self.game['player']
        vehicle = player.get('vehicle')
        if vehicle:
            self.send_packet(
                "player_look",
                self.buff_type.pack(
                    'ff?',
                    player['yaw'],
                    player['pitch'],
                    player['on_ground']))
            self.send_packet(
                "steer_vehicle",
                self.buff_type.pack('ffb', 0, 0, 0))
            self.send_packet(
                "vehicle_move",
                self.buff_type.pack(
                    'dddff',
                    player['x'],
                    player['y'],
                    player['z'],
                    player['yaw'],
                    player['pitch']))
        else:
            self.send_packet(
                "player",
                self.buff_type.pack('?', player['on_ground']))

    def update_player_full(self):
        player = self.game['player']
        vehicle = player.get('vehicle')
        if vehicle:
            pass
        else:
            self.send_packet(
                "player_position_and_look",
                self.buff_type.pack(
                    'dddff?',
                    player['x'],
                    player['y'],
                    player['z'],
                    player['yaw'],
                    player['pitch'],
                    player['on_ground']))

    # Synchronization logic ---------------------------------------------------

    def attach(self):
        bt = self.buff_type

        # Send 'Join Game'
        downstream.send_packet(
            'join_game',
            bt.pack(
                'ibibb',
                self.game['player']['id'],
                self.game['game_mode'],
                self.game['dimension'],
                self.game['difficulty'],
                self.game['max_players']),
            bt.pack_string(self.game['level_type']),
            bt.pack('?', self.game['reduced_debug_info']))

        # Send 'Plugin Message'
        if self.game['channels']:
            downstream.send_packet(
                'plugin_message',
                bt.pack_string('REGISTER'),
                b"\x00".join(self.game['channels']))
        downstream.send_packet(
            'plugin_message',
            bt.pack_string('MC|Brand'),
            bt.pack_string(self.game['brand']))

        # Send 'Spawn Position'
        downstream.send_packet(
            'spawn_position',
            bt.pack_position(*self.game['spawn_position']))

        # Send 'Player Abilities'
        downstream.send_packet(
            'player_abilities',
            bt.pack(
                'Bff',
                self.game['abilities']['invulnerable']  << 0 |
                self.game['abilities']['flying']        << 1 |
                self.game['abilities']['allow_flying']  << 2 |
                self.game['abilities']['creative_mode'] << 3,
                self.game['abilities']['flying_speed'],
                self.game['abilities']['fov_modifier']))

        # Send 'Window Items'
        downstream.send_packet(
            'window_items',
            bt.pack('Bh', 0, len(self.game['inventory'])),
            *[bt.pack_slot(**item)
              for item in self.game['inventory']])

        # Send 'Held Item Change'
        downstream.send_packet(
            'held_item_change',
            bt.pack('B', self.game['held_item']))

        # Send 'Unlock Recipes'
        downstream.send_packet(
            'unlock_recipes',
            bt.pack_varint(0),
            bt.pack('??', False, False),
            bt.pack_varint(len(self.game['recipes'])),
            b"".join(bt.pack_varint(recipe_id)
                     for recipe_id in self.game['recipes']),
            bt.pack_varint(0))

        # Send 'Update Health'
        downstream.send_packet(
            'update_health',
            bt.pack('f', self.game['health']),
            bt.pack_varint(self.game['food']),
            bt.pack('f', self.game['food_saturation']))

        # Send 'Set Experience'
        downstream.send_packet(
            'set_experience',
            bt.pack('f', self.game['experience_bar']),
            bt.pack_varint(self.game['experience_level']),
            bt.pack_varint(self.game['experience_total']))

        # Send 'Time Update'
        downstream.send_packet(
            'time_update',
            bt.pack('q', self.game['time_world']),
            bt.pack('q', self.game['time_day']))

        # Send 'World Border'
        downstream.send_packet(
            'world_border',
            bt.pack_varint(3),
            bt.pack(
                'dddd',
                self.game['world_border']['x'],
                self.game['world_border']['z'],
                self.game['world_border']['old_diameter'],
                self.game['world_border']['new_diameter']),
            bt.pack_varint(self.game['world_border']['speed'], max_bits=64),
            bt.pack_varint(self.game['world_border']
                           ['portal_teleport_boundary']),
            bt.pack_varint(self.game['world_border']['warning_time']),
            bt.pack_varint(self.game['world_border']['warning_blocks']))

        # Send 'Change Game State'
        if self.game['raining']:
            downstream.send_packet('change_game_state', bt.pack('bf', 2, 0))

        # Send 'Chunk Data'
        for coords, chunk in self.game['chunks'].items():
            x, z = coords

            bitmask = 0
            data = b""
            for i, section in enumerate(chunk['sections']):
                if not section[0].is_empty():
                    bitmask |= 1 << i
                    data += bt.pack_chunk_section(*section)
            data += bt.pack('B'*256, *chunk['biomes'])

            downstream.send_packet(
                'chunk_data',
                bt.pack('ii?', x, z, True),
                bt.pack_varint(bitmask),
                bt.pack_varint(len(data)),
                data,
                bt.pack_varint(len(chunk['block_entities'])),
                *[bt.pack_nbt(entity)
                  for entity in chunk['block_entities'].values()])

        # Spawn entities
        for entity in self.game['entities'].values():
            # Send 'Spawn Player'
            if entity['type'] == 'player':
                downstream.send_packet(
                    'spawn_player',
                    bt.pack_varint(entity['id']),
                    bt.pack_uuid(entity['uuid']),
                    bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    bt.pack('BB', f2b(entity['yaw']), f2b(entity['pitch'])),
                    bt.pack_entity_metadata(entity['metadata']))

            # Send 'Spawn Mob'
            elif entity['type'] == 'mob':
                downstream.send_packet(
                    'spawn_mob',
                    bt.pack_varint(entity['id']),
                    bt.pack_uuid(entity['uuid']),
                    bt.pack_varint(entity['mob_type']),
                    bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    bt.pack(
                        'BBB',
                        f2b(entity['yaw']),
                        f2b(entity['pitch']),
                        f2b(entity['head_pitch'])),
                    bt.pack('hhh', entity['dx'], entity['dy'], entity['dz']),
                    bt.pack_entity_metadata(entity['metadata']))

            # Send 'Spawn Object'
            elif entity['type'] == 'object':
                downstream.send_packet(
                    'spawn_object',
                    bt.pack_varint(entity['id']),
                    bt.pack_uuid(entity['uuid']),
                    bt.pack('b', entity['object_type']),
                    bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    bt.pack('BB', f2b(entity['pitch']), f2b(entity['yaw'])),
                    bt.pack('i', entity['object_data']),
                    bt.pack('hhh', entity['dx'], entity['dy'], entity['dz']))

            # Send 'Spawn Painting'
            elif entity['type'] == 'painting':
                downstream.send_packet(
                    'spawn_painting',
                    bt.pack_varint(entity['id']),
                    bt.pack_uuid(entity['uuid']),
                    bt.pack_string(entity['painting_type']),
                    bt.pack_position(entity['x'], entity['y'], entity['z']),
                    bt.pack('b', entity['painting_direction']))

            # Send 'Spawn Global Entity'
            elif entity['type'] == 'global_entity':
                downstream.send_packet(
                    'spawn_global_entity',
                    bt.pack_varint(entity['id']),
                    bt.pack('b', entity['global_entity_type']),
                    bt.pack('ddd', entity['x'], entity['y'], entity['z']))

            # Send 'Spawn Experience Orb'
            elif entity['type'] == 'experience_orb':
                downstream.send_packet(
                    'spawn_experience_orb',
                    bt.pack_varint(entity['id']),
                    bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    bt.pack('h', entity['experience_count']))

        # Set up entities
        for entity in self.game['entities'].values():
            # Send 'Entity Equipment'
            for idx, equipment in enumerate(entity.get('equipment', [])):
                if equipment['id'] != -1:
                    downstream.send_packet(
                        'entity_equipment',
                        bt.pack_varint(entity['id']),
                        bt.pack_varint(idx),
                        bt.pack_slot(**equipment))

            # Send 'Entity Effects'
            for effect in entity.get('effects', {}).values():
                downstream.send_packet(
                    'entity_effect',
                    bt.pack_varint(entity['id']),
                    bt.pack('bb', effect['id'], effect['amplifier']),
                    bt.pack_varint(effect['duration']),
                    bt.pack('b', effect['flags']))

            # Send 'Entity Properties'
            properties = entity.get('properties', {})
            if properties:
                out = b""
                for property in properties.values():
                    out += bt.pack_string(property["key"])
                    out += bt.pack('d', property["value"])
                    out += bt.pack_varint(len(property["modifiers"]))
                    for modifier in property["modifiers"]:
                        out += bt.pack_uuid(modifier["uuid"])
                        out += bt.pack('d', modifier["amount"])
                        out += bt.pack('b', modifier["operation"])

                downstream.send_packet(
                    'entity_properties',
                    bt.pack_varint(entity['id']),
                    bt.pack('i', len(properties)),
                    out)

            # Send 'Set Passengers'
            passengers = entity.get('passengers', [])
            if passengers:
                downstream.send_packet(
                    'set_passengers',
                    bt.pack_varint(entity['id']),
                    bt.pack_varint(len(passengers)),
                    *[bt.pack_varint(passenger) for passenger in passengers])

            # Send 'Attach Entity'
            attached = entity.get('attached')
            if attached:
                downstream.send_packet(
                    'entity_attach',
                    bt.pack_varint(entity['id']),
                    bt.pack_varint(attached))

            # Send 'Use Bed'
            bed = entity.get('bed')
            if bed:
                downstream.send_packet(
                    'use_bed',
                    bt.pack_varint(entity['id']),
                    bt.pack_position(*bed))

            # Send 'Entity Head Look'
            head_yaw = entity.get('head_yaw')
            if head_yaw:
                downstream.send_packet(
                    'entity_head_look',
                    bt.pack_varint(entity['id']),
                    bt.pack('B', f2b(head_yaw)))

        # Send 'Player List Header and Footer'
        players_header_footer = self.game.get('players_header_footer')
        if players_header_footer:
            downstream.send_packet(
                'player_list_header_footer',
                bt.pack_chat(players_header_footer[0]),
                bt.pack_chat(players_header_footer[1]))

        # Send 'Player List Item'
        data = b""
        for player in self.game['players'].values():
            data += bt.pack_uuid(player['uuid'])
            data += bt.pack_string(player['name'])
            data += bt.pack_varint(len(player['properties']))
            for property in player['properties']:
                data += bt.pack_string(property['name'])
                data += bt.pack_string(property['value'])
                data += bt.pack_optional(bt.pack_string, property['signature'])
            data += bt.pack_varint(player['game_mode'])
            data += bt.pack_varint(player['ping'])
            data += bt.pack_optional(bt.pack_chat, player['display_name'])

        downstream.send_packet(
            'player_list_item',
            bt.pack_varint(0),
            bt.pack_varint(len(self.game['players'])),
            data)

        # Send 'Boss Bar'
        for boss_bar in self.game['boss_bars'].values():
            downstream.send_packet(
                'boss_bar',
                bt.pack_uuid(boss_bar['uuid']),
                bt.pack_varint(0),
                bt.pack_chat(boss_bar['title']),
                bt.pack('f', boss_bar['health']),
                bt.pack_varint(boss_bar['color']),
                bt.pack_varint(boss_bar['dividers']),
                bt.pack('B', boss_bar['flags']))

        # Send 'Player Position and Look'
        downstream.send_packet(
            'player_position_and_look',
            bt.pack(
                'dddff',
                self.game['player']['x'],
                self.game['player']['y'],
                self.game['player']['z'],
                self.game['player']['yaw'],
                self.game['player']['pitch']),
            bt.pack('b', 0),
            bt.pack_varint(0))

        # Send 'Resource Pack Send'
        if self.game['resource_pack']['url']:
            downstream.send_packet(
                'resource_pack_send',
                bt.pack_string(self.game['resource_pack']['url']),
                bt.pack_string(self.game['resource_pack']['hash']))

        # Send 'Chat Message'
        messages = self.game['chat_messages']
        if messages:
            messages.append(u"\u00a7a--- end scrollback ---")
        for message in messages:
            downstream.send_packet(
                'chat_message',
                bt.pack_chat(message),
                bt.pack('b', 0))
        del messages[:]

        self.start_forwarding()

    def detach(self):
        bt = self.buff_type

        actions = [
            (1, "sneaking"),
            (4, "sprinting"),
            (6, "horse_jumping"),
        ]

        for action_id, field in actions:
            if self.game['player']['actions'].get(field, False):
                self.send_packet(
                    'entity_action',
                    bt.pack_varint(self.game['player']['id']),
                    bt.pack_varint(action_id))

        self.stop_forwarding()

    # Packet handlers ---------------------------------------------------------

    def packet_received(self, buff, name):
        if self.forwarding:
            buff.save()
            downstream.send_packet(name, buff.read())
            buff.restore()
        super(Upstream, self).packet_received(buff, name)

    # Basic config ------------------------------------------------------------

    def packet_join_game(self, buff):
        self.game['player'] = {
            'id': buff.unpack('i'),
            'type': 'client',
            'on_ground': True,
            'actions': {}}
        self.game['game_mode'] = buff.unpack('b')
        self.game['dimension'] = buff.unpack('i')
        self.game['difficulty'] = buff.unpack('b')
        self.game['max_players'] = buff.unpack('b')
        self.game['level_type'] = buff.unpack_string()
        self.game['reduced_debug_info'] = buff.unpack('?')
        self.game['entities'][self.game['player']['id']] = self.game['player']

    def packet_respawn(self, buff):
        self.game['dimension'] = buff.unpack('i')
        self.game['difficulty'] = buff.unpack('b')
        self.game['game_mode'] = buff.unpack('b')
        self.game['level_type'] = buff.unpack_string()

    def packet_server_difficulty(self, buff):
        self.game['difficulty'] = buff.unpack('b')

    def packet_change_game_state(self, buff):
        reason, value = buff.unpack('bf')
        if reason == 1:
            self.game['raining'] = False
        elif reason == 2:
            self.game['raining'] = True
        elif reason == 3:
            self.game['game_mode'] = value

    # Spawn position ----------------------------------------------------------

    def packet_spawn_position(self, buff):
        self.game['spawn_position'] = buff.unpack_position()

    # Abilities ---------------------------------------------------------------

    def packet_player_abilities(self, buff):
        flags = buff.unpack('B')
        self.game['abilities']['invulnerable']  = bool(flags & 1)
        self.game['abilities']['flying']        = bool(flags & 2)
        self.game['abilities']['allow_flying']  = bool(flags & 4)
        self.game['abilities']['creative_mode'] = bool(flags & 8)
        self.game['abilities']['flying_speed']  = buff.unpack('f')
        self.game['abilities']['fov_modifier']  = buff.unpack('f')

    # Inventory ---------------------------------------------------------------

    def packet_window_items(self, buff):
        window_id, count = buff.unpack('bh')
        slots = [buff.unpack_slot() for _ in range(count)]
        if window_id == 0:
            self.game['inventory'][:] = slots

    def packet_set_slot(self, buff):
        window_id, idx = buff.unpack('bh')
        slot = buff.unpack_slot()
        if window_id == 0:
            self.game['inventory'][idx] = slot

    def packet_held_item_change(self, buff):
        self.game['held_item'] = buff.unpack('B')

    def packet_unlock_recipes(self, buff):
        action = buff.unpack_varint()
        crafting_book_open, filtering_craftable = buff.unpack('??')

        if action == 0:
            for _ in range(buff.unpack_varint()):
                self.game['recipes'].add(buff.unpack_varint())
            for _ in range(buff.unpack_varint()):
                self.game['recipes'].add(buff.unpack_varint())
        elif action == 1:
            for _ in range(buff.unpack_varint()):
                self.game['recipes'].add(buff.unpack_varint())
        elif action == 2:
            for _ in range(buff.unpack_varint()):
                self.game['recipes'].remove(buff.unpack_varint())

    # Health ------------------------------------------------------------------

    def packet_update_health(self, buff):
        self.game['health'] = buff.unpack('f')
        self.game['food'] = buff.unpack_varint()
        self.game['food_saturation'] = buff.unpack('f')

    # Experience --------------------------------------------------------------

    def packet_set_experience(self, buff):
        self.game['experience_bar'] = buff.unpack('f')
        self.game['experience_level'] = buff.unpack_varint()
        self.game['experience_total'] = buff.unpack_varint()

    # Time --------------------------------------------------------------------

    def packet_time_update(self, buff):
        self.game['time_world'] = buff.unpack('q')
        self.game['time_day'] = buff.unpack('q')

    # World border ------------------------------------------------------------

    def packet_world_border(self, buff):
        action = buff.unpack_varint()
        if action == 0:
            _ = buff.unpack('d')
        elif action == 1:
            self.game['world_border']['old_diameter'] = buff.unpack('d')
            self.game['world_border']['new_diameter'] = buff.unpack('d')
            self.game['world_border']['speed'] = buff.unpack_varint()
        elif action == 2:
            self.game['world_border']['x'] = buff.unpack('d')
            self.game['world_border']['z'] = buff.unpack('d')
        elif action == 3:
            self.game['world_border']['x'] = buff.unpack('d')
            self.game['world_border']['z'] = buff.unpack('d')
            self.game['world_border']['old_diameter'] = buff.unpack('d')
            self.game['world_border']['new_diameter'] = buff.unpack('d')
            self.game['world_border']['speed'] = buff.unpack_varint()
            self.game['world_border']['portal_teleport_boundary'] = \
                buff.unpack_varint()
            self.game['world_border']['warning_time'] = buff.unpack_varint()
            self.game['world_border']['warning_blocks'] = buff.unpack_varint()
        elif action == 4:
            self.game['world_border']['warning_time'] = buff.unpack_varint()
        elif action == 5:
            self.game['world_border']['warning_blocks'] = buff.unpack_varint()

    # Chunks ------------------------------------------------------------------

    def packet_chunk_data(self, buff):
        x, z, contiguous = buff.unpack('ii?')
        bitmask = buff.unpack_varint()
        size = buff.unpack_varint()

        if contiguous:
            chunk = self.game['chunks'][x, z] = {
                'sections': [None]*16,
                'block_entities': {}}
        else:
            chunk = self.game['chunks'][x, z]

        for idx in range(16):
            if bitmask & (1 << idx):
                section = buff.unpack_chunk_section(
                    self.game['dimension'] == 0)
            elif self.game['dimension'] == 0:
                section = (BlockArray.empty(), LightArray.empty(),
                           LightArray.empty())
            else:
                section = (BlockArray.empty(), LightArray.empty())

            chunk['sections'][idx] = section

        if contiguous:
            chunk['biomes'] = buff.unpack('B'*256)

        for _ in range(buff.unpack_varint()):
            block_entity = buff.unpack_nbt()
            block_entity_obj = block_entity.to_obj()[""]
            chunk['block_entities'][
                block_entity_obj['x'],
                block_entity_obj['y'],
                block_entity_obj['z']] = block_entity

    def packet_unload_chunk(self, buff):
        x, z = buff.unpack('ii')
        if (x, z) in self.game['chunks']:
            del self.game['chunks'][x, z]

    def packet_block_change(self, buff):
        x, y, z = buff.unpack_position()
        block_id = buff.unpack_varint()
        self.set_block(x, y, z, block_id)

    def packet_multi_block_change(self, buff):
        chunk_x, chunk_z = buff.unpack('ii')
        for _ in range(buff.unpack_varint()):
            block_xz, block_y = buff.unpack('BB')
            block_id = buff.unpack_varint()
            self.set_block(
                16*chunk_x + block_xz >> 4,
                block_y,
                16*chunk_z + block_xz & 0x0F,
                block_id)

    def packet_explosion(self, buff):
        x, y, z, radius = buff.unpack('ffff')
        for _ in range(buff.unpack('i')):
            dx, dy, dz = buff.unpack('bbb')
            self.set_block(x + dx, y + dy, z + dz, 0)
        px, py, pz = buff.unpack('fff')

    def packet_update_block_entity(self, buff):
        x, y, z = buff.unpack_position()
        action = buff.unpack('B')
        new_tag = buff.unpack_nbt()

        chunk_x, chunk_z = x // 16, z // 16
        block_entities = self.game['chunks'][chunk_x, chunk_z][
                             'block_entities']
        old_tag = block_entities.get((x, y, z))

        if old_tag and not new_tag:
            del block_entities[x, y, z]
        elif not old_tag and new_tag:
            block_entities[x, y, z] = new_tag
        elif old_tag and new_tag:
            old_tag.update(new_tag)

    # Entity Spawn ------------------------------------------------------------

    def packet_spawn_player(self, buff):
        entity = {'type': 'player'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'], entity['pitch'] = buff.unpack('BB')
        entity['metadata'] = buff.unpack_entity_metadata()
        self.game['entities'][entity['id']] = entity

    def packet_spawn_mob(self, buff):
        entity = {'type': 'mob'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['mob_type'] = buff.unpack_varint()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['head_pitch'] = b2f(buff.unpack('B'))
        entity['dx'], entity['dy'], entity['dz'] = buff.unpack('hhh')
        entity['metadata'] = buff.unpack_entity_metadata()
        self.game['entities'][entity['id']] = entity

    def packet_spawn_object(self, buff):
        entity = {'type': 'object'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['object_type'] = buff.unpack_varint()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['object_data'] = buff.unpack('i')
        entity['dx'], entity['dy'], entity['dz'] = buff.unpack('hhh')
        self.game['entities'][entity['id']] = entity

    def packet_spawn_painting(self, buff):
        entity = {'type': 'painting'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['painting_type'] = buff.unpack_string()
        entity['x'], entity['y'], entity['z'] = buff.unpack_position()
        entity['painting_direction'] = buff.unpack('b')
        self.game['entities'][entity['id']] = entity

    def packet_spawn_global_entity(self, buff):
        entity = {'type': 'global_entity'}
        entity['id'] = buff.unpack_varint()
        entity['global_entity_type'] = buff.unpack('b')
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        self.game['entities'][entity['id']] = entity

    def packet_spawn_experience_orb(self, buff):
        entity = {'type': 'experience_orb'}
        entity['id'] = buff.unpack_varint()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['experience_count'] = buff.unpack('h')
        self.game['entities'][entity['id']] = entity

    def packet_destroy_entities(self, buff):
        for _ in range(buff.unpack_varint()):
            del self.game['entities'][buff.unpack_varint()]

    # Entity position ---------------------------------------------------------

    def packet_entity_teleport(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')

    def packet_entity_look_and_relative_move(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['x'] += buff.unpack('h')
        entity['y'] += buff.unpack('h')
        entity['z'] += buff.unpack('h')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')

    def packet_entity_look(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')

    def packet_entity_relative_move(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['x'] += buff.unpack('h')
        entity['y'] += buff.unpack('h')
        entity['z'] += buff.unpack('h')
        entity['on_ground'] = buff.unpack('?')

    def packet_entity_velocity(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['dx'], entity['dy'], entity['dz'] = buff.unpack('hhh')

    def packet_entity_head_look(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['head_yaw'] = b2f(buff.unpack('B'))

    # Entity misc -------------------------------------------------------------

    def packet_entity_metadata(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        if 'metadata' not in entity:
            entity['metadata'] = {}
        for ty_key, val in buff.unpack_entity_metadata().items():
            entity['metadata'][ty_key] = val

    def packet_entity_effect(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        if 'effects' not in entity:
            entity['effects'] = {}
        effect = {}
        effect['id'] = buff.unpack('b')
        effect['amplifier'] = buff.unpack('b')
        effect['duration'] = buff.unpack_varint()
        effect['flags'] = buff.unpack('b')
        entity['effects'][effect['id']] = effect

    def packet_remove_entity_effect(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        del entity['effects'][buff.unpack('b')]

    def packet_entity_equipment(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        if 'equipment' not in entity:
            entity['equipment'] = [{'id': -1} for _ in range(6)]
        idx = buff.unpack_varint()
        entity['equipment'][idx] = buff.unpack_slot()

    def packet_set_passengers(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        count = buff.unpack_varint()
        entity['passengers'] = [buff.unpack_varint() for _ in range(count)]
        if self.game['player']['id'] in entity['passengers']:
            self.game['player']['vehicle'] = entity['id']
        elif self.game['player'].get('vehicle') == entity['id']:
            self.game['player']['vehicle'] = None

    def packet_attach_entity(self, buff):
        entity = self.game['entities'][buff.unpack('i')]
        other = buff.unpack('i')
        if other == -1:
            entity['attached'] = None
        else:
            entity['attached'] = other

    def packet_entity_properties(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        if 'properties' not in entity:
            entity['properties'] = {}
        for _ in range(buff.unpack('i')):
            property = {}
            property['key'] = buff.unpack_string()
            property['value'] = buff.unpack('d')
            property['modifiers'] = []
            for __ in range(buff.unpack_varint()):
                modifier = {}
                modifier['uuid'] = buff.unpack_uuid()
                modifier['amount'] = buff.unpack('d')
                modifier['operation'] = buff.unpack('b')
                property['modifiers'].append(modifier)
            entity['properties'][property['key']] = property

    def packet_use_bed(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        entity['bed'] = buff.unpack_position()

    def packet_animation(self, buff):
        entity = self.game['entities'][buff.unpack_varint()]
        animation = buff.unpack('b')
        if animation == 2:
            entity['bed'] = None

    # Player list -------------------------------------------------------------

    def packet_player_list_item(self, buff):
        action = buff.unpack_varint()
        for _ in range(buff.unpack_varint()):
            uuid = buff.unpack_uuid()

            # Delete entry
            if action == 4:
                if uuid in self.game['players']:
                    del self.game['players'][uuid]
                continue

            # Update entry
            elif uuid in self.game['players']:
                player = self.game['players'][uuid]

            # Create entry
            elif action == 0:
                player = self.game['players'][uuid] = {'uuid': uuid}

            # Invalid data from server
            else:
                buff.discard()
                continue

            # Read fields
            if action == 0:
                player['name'] = buff.unpack_string()
                player['properties'] = []
                for __ in range(buff.unpack_varint()):
                    property = {}
                    property['name'] = buff.unpack_string()
                    property['value'] = buff.unpack_string()
                    property['signature'] = buff.unpack_optional(
                        buff.unpack_string)
                    player['properties'].append(property)
                player['game_mode'] = buff.unpack_varint()
                player['ping'] = buff.unpack_varint()
                player['display_name'] = buff.unpack_optional(buff.unpack_chat)
            elif action == 1:
                player['game_mode'] = buff.unpack_varint()
            elif action == 2:
                player['ping'] = buff.unpack_varint()
            elif action == 3:
                player['display_name'] = buff.unpack_optional(buff.unpack_chat)

    def packet_player_list_header_footer(self, buff):
        self.game['players_header_footer'] = buff.unpack_chat(), \
                                             buff.unpack_chat()

    # Boss bars ---------------------------------------------------------------

    def packet_boss_bar(self, buff):
        uuid = buff.unpack_uuid()
        action = buff.unpack_varint()
        if action == 0:
            # Create boss bar
            self.game['boss_bars'][uuid] = {'uuid': uuid}
        elif action == 1:
            del self.game['boss_bars'][uuid]
            return

        boss_bar = self.game['boss_bars'][uuid]

        if action == 0:
            boss_bar['title'] = buff.unpack_chat()
            boss_bar['health'] = buff.unpack('f')
            boss_bar['color'] = buff.unpack_varint()
            boss_bar['dividers'] = buff.unpack_varint()
            boss_bar['flags'] = buff.unpack('B')
        elif action == 2:
            boss_bar['health'] = buff.unpack('f')
        elif action == 3:
            boss_bar['title'] = buff.unpack_chat()
        elif action == 4:
            boss_bar['color'] = buff.unpack_varint()
            boss_bar['dividers'] = buff.unpack_varint()
        elif action == 5:
            boss_bar['flags'] = buff.unpack('B')

    # Resource packs ----------------------------------------------------------

    def packet_resource_pack_send(self, buff):
        resource_pack = {}
        resource_pack['url'] = buff.unpack_string()
        resource_pack['hash'] = buff.unpack_string()
        self.game['resource_pack'].update(resource_pack)

    # Chat --------------------------------------------------------------------

    def packet_chat_message(self, buff):
        message = buff.unpack_chat()
        position = buff.unpack('b')
        if position in (0, 1):
            self.game['chat_messages'].append(message)
            if len(self.game['chat_messages']) > scrollback_limit:
                self.game['chat_messages'].pop(0)

    # Plugin messages ---------------------------------------------------------

    def packet_plugin_message(self, buff):
        channel = buff.unpack_string()

        if channel in ("REGISTER", "UNREGISTER"):
            channels = set(buff.read().split(b"\x00"))
            if channel == "REGISTER":
                self.game['channels'] |= channels
            else:
                self.game['channels'] -= channels

        elif channel == "MC|Brand":
            self.game["brand"] = buff.unpack_string()

    # AFK Handling ------------------------------------------------------------

    def packet_player_position_and_look(self, buff):
        pos_look = buff.unpack('dddff')
        flags = buff.unpack('B')
        keys = ("x", "y", "z", "yaw", "pitch")

        for idx, key in enumerate(keys):
            if flags & (1 << idx):
                self.game['player'][key] += pos_look[idx]
            else:
                self.game['player'][key] = pos_look[idx]

        teleport_id = buff.unpack_varint()

        if not self.forwarding:
            self.send_packet(
                "teleport_confirm",
                self.buff_type.pack_varint(teleport_id))

        if not self.spawned:
            self.player_spawned()

    def packet_vehicle_move(self, buff):
        player = self.game['player']
        vehicle = self.game['entities'][player['vehicle']]

        player['x'] = vehicle['x'] = buff.unpack('d')
        player['y'] = vehicle['y'] = buff.unpack('d')
        player['z'] = vehicle['z'] = buff.unpack('d')
        player['yaw'] = vehicle['yaw'] = buff.unpack('f')
        player['pitch'] = vehicle['pitch'] = buff.unpack('f')

    def packet_keep_alive(self, buff):
        id = buff.unpack('q')
        if not self.forwarding:
            self.send_packet("keep_alive", self.buff_type.pack('q', id))


class UpstreamFactory(ClientFactory, ReconnectingClientFactory):
    protocol = Upstream
    force_protocol_version = protocol_version
    log_level = log_level


@defer.inlineCallbacks
def run():
    cache_path = os.path.join(os.path.dirname(__file__), "cache.json")
    if os.path.exists(cache_path):
        profile = yield Profile.from_file(profiles_path=cache_path)
    elif email and password:
        profile = yield Profile.from_credentials(email, password)
        profile.to_file(profiles_path=cache_path)
    else:
        profile = yield OfflineProfile.from_display_name(username)
    downstream_factory = DownstreamFactory()
    downstream_factory.listen(listen_host, listen_port)
    upstream_factory = UpstreamFactory(profile)
    upstream_factory.connect(connect_host, connect_port)


if __name__ == "__main__":
    run()
    reactor.run()
