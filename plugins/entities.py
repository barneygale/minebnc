from collections import defaultdict
from plugins import Plugin


def f2b(n):
    return int((n % 360.0) * 256.0 / 360.0)


def b2f(n):
    return n * 360.0 / 256.0


class EntitiesPlugin(Plugin):
    def setup(self):
        self.entities = defaultdict(lambda: {
            "type": "unknown",
            "x": 0,
            "y": 0,
            "z": 0,
        })
        self.player = {
            'type': 'client',
            'id': 0,
            'x': 0,
            'y': 0,
            'z': 0,
            'yaw': 0,
            'pitch': 0,
            'on_ground': True,
            'actions': {},
        }
        self.spawned = False

    def attach(self):
        for entity in self.entities.values():
            # Send 'Spawn Player'
            if entity['type'] == 'player':
                self.downstream.send_packet(
                    'spawn_player',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_uuid(entity['uuid']),
                    self.bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    self.bt.pack('BB', f2b(entity['yaw']), f2b(entity['pitch'])),
                    self.bt.pack_entity_metadata(entity['metadata']))

            # Send 'Spawn Mob'
            elif entity['type'] == 'mob':
                self.downstream.send_packet(
                    'spawn_mob',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_uuid(entity['uuid']),
                    self.bt.pack_varint(entity['mob_type']),
                    self.bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    self.bt.pack(
                        'BBB',
                        f2b(entity['yaw']),
                        f2b(entity['pitch']),
                        f2b(entity['head_pitch'])),
                    self.bt.pack('hhh', entity['dx'], entity['dy'], entity['dz']),
                    self.bt.pack_entity_metadata(entity['metadata']))

            # Send 'Spawn Object'
            elif entity['type'] == 'object':
                self.downstream.send_packet(
                    'spawn_object',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_uuid(entity['uuid']),
                    self.bt.pack('b', entity['object_type']),
                    self.bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    self.bt.pack('BB', f2b(entity['pitch']), f2b(entity['yaw'])),
                    self.bt.pack('i', entity['object_data']),
                    self.bt.pack('hhh', entity['dx'], entity['dy'], entity['dz']))

            # Send 'Spawn Painting'
            elif entity['type'] == 'painting':
                self.downstream.send_packet(
                    'spawn_painting',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_uuid(entity['uuid']),
                    self.bt.pack_string(entity['painting_type']),
                    self.bt.pack_position(entity['x'], entity['y'], entity['z']),
                    self.bt.pack('b', entity['painting_direction']))

            # Send 'Spawn Global Entity'
            elif entity['type'] == 'global_entity':
                self.downstream.send_packet(
                    'spawn_global_entity',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack('b', entity['global_entity_type']),
                    self.bt.pack('ddd', entity['x'], entity['y'], entity['z']))

            # Send 'Spawn Experience Orb'
            elif entity['type'] == 'experience_orb':
                self.downstream.send_packet(
                    'spawn_experience_orb',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack('ddd', entity['x'], entity['y'], entity['z']),
                    self.bt.pack('h', entity['experience_count']))

        # Set up entities
        for entity in self.entities.values():
            # Send 'Entity Equipment'
            for idx, equipment in enumerate(entity.get('equipment', [])):
                if equipment['id'] != -1:
                    self.downstream.send_packet(
                        'entity_equipment',
                        self.bt.pack_varint(entity['id']),
                        self.bt.pack_varint(idx),
                        self.bt.pack_slot(**equipment))

            # Send 'Entity Effects'
            for effect in entity.get('effects', {}).values():
                self.downstream.send_packet(
                    'entity_effect',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack('bb', effect['id'], effect['amplifier']),
                    self.bt.pack_varint(effect['duration']),
                    self.bt.pack('b', effect['flags']))

            # Send 'Entity Properties'
            properties = entity.get('properties', {})
            if properties:
                out = b""
                for property in properties.values():
                    out += self.bt.pack_string(property["key"])
                    out += self.bt.pack('d', property["value"])
                    out += self.bt.pack_varint(len(property["modifiers"]))
                    for modifier in property["modifiers"]:
                        out += self.bt.pack_uuid(modifier["uuid"])
                        out += self.bt.pack('d', modifier["amount"])
                        out += self.bt.pack('b', modifier["operation"])

                self.downstream.send_packet(
                    'entity_properties',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack('i', len(properties)),
                    out)

            # Send 'Set Passengers'
            passengers = entity.get('passengers', [])
            if passengers:
                self.downstream.send_packet(
                    'set_passengers',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_varint(len(passengers)),
                    *[self.bt.pack_varint(passenger) for passenger in passengers])

            # Send 'Attach Entity'
            attached = entity.get('attached')
            if attached:
                self.downstream.send_packet(
                    'entity_attach',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_varint(attached))

            # Send 'Use Bed'
            bed = entity.get('bed')
            if bed:
                self.downstream.send_packet(
                    'use_bed',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack_position(*bed))

            # Send 'Entity Head Look'
            head_yaw = entity.get('head_yaw')
            if head_yaw:
                self.downstream.send_packet(
                    'entity_head_look',
                    self.bt.pack_varint(entity['id']),
                    self.bt.pack('B', f2b(head_yaw)))

        # Send 'Player Position And Look'
        self.downstream.send_packet(
        'player_position_and_look',
            self.bt.pack(
            'dddff',
            self.player['x'],
            self.player['y'],
            self.player['z'],
            self.player['yaw'],
            self.player['pitch']),
            self.bt.pack('b', 0),
            self.bt.pack_varint(0))

    def detach(self):
        actions = [
            (1, "sneaking"),
            (4, "sprinting"),
            (6, "horse_jumping"),
        ]

        for action_id, field in actions:
            if self.player['actions'].get(field, False):
                self.upstream.send_packet(
                    'entity_action',
                    self.bt.pack_varint(self.player['id']),
                    self.bt.pack_varint(action_id))

    # Entity spawning ---------------------------------------------------------

    def packet_downstream_join_game(self, buff):
        self.player['id'] = buff.unpack('i')
        self.entities[self.player['id']] = self.player
        buff.discard()

    def packet_downstream_spawn_player(self, buff):
        entity = {'type': 'player'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'], entity['pitch'] = buff.unpack('BB')
        entity['metadata'] = buff.unpack_entity_metadata()
        self.entities[entity['id']] = entity

    def packet_downstream_spawn_mob(self, buff):
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
        self.entities[entity['id']] = entity

    def packet_downstream_spawn_object(self, buff):
        entity = {'type': 'object'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['object_type'] = buff.unpack_varint()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['object_data'] = buff.unpack('i')
        entity['dx'], entity['dy'], entity['dz'] = buff.unpack('hhh')
        self.entities[entity['id']] = entity

    def packet_downstream_spawn_painting(self, buff):
        entity = {'type': 'painting'}
        entity['id'] = buff.unpack_varint()
        entity['uuid'] = buff.unpack_uuid()
        entity['painting_type'] = buff.unpack_string()
        entity['x'], entity['y'], entity['z'] = buff.unpack_position()
        entity['painting_direction'] = buff.unpack('b')
        self.entities[entity['id']] = entity

    def packet_downstream_spawn_global_entity(self, buff):
        entity = {'type': 'global_entity'}
        entity['id'] = buff.unpack_varint()
        entity['global_entity_type'] = buff.unpack('b')
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        self.entities[entity['id']] = entity

    def packet_downstream_spawn_experience_orb(self, buff):
        entity = {'type': 'experience_orb'}
        entity['id'] = buff.unpack_varint()
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['experience_count'] = buff.unpack('h')
        self.entities[entity['id']] = entity

    def packet_downstream_destroy_entities(self, buff):
        for _ in range(buff.unpack_varint()):
            del self.entities[buff.unpack_varint()]


    # Entity position ---------------------------------------------------------

    def packet_downstream_entity_teleport(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['x'], entity['y'], entity['z'] = buff.unpack('ddd')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')


    def packet_downstream_entity_look_and_relative_move(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['x'] += buff.unpack('h')
        entity['y'] += buff.unpack('h')
        entity['z'] += buff.unpack('h')
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')


    def packet_downstream_entity_look(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['yaw'] = b2f(buff.unpack('B'))
        entity['pitch'] = b2f(buff.unpack('B'))
        entity['on_ground'] = buff.unpack('?')


    def packet_downstream_entity_relative_move(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['x'] += buff.unpack('h')
        entity['y'] += buff.unpack('h')
        entity['z'] += buff.unpack('h')
        entity['on_ground'] = buff.unpack('?')


    def packet_downstream_entity_velocity(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['dx'], entity['dy'], entity['dz'] = buff.unpack('hhh')


    def packet_downstream_entity_head_look(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['head_yaw'] = b2f(buff.unpack('B'))


    # Entity misc -------------------------------------------------------------

    def packet_downstream_entity_metadata(self, buff):
        entity = self.entities[buff.unpack_varint()]
        if 'metadata' not in entity:
            entity['metadata'] = {}
        for ty_key, val in buff.unpack_entity_metadata().items():
            entity['metadata'][ty_key] = val


    def packet_downstream_entity_effect(self, buff):
        entity = self.entities[buff.unpack_varint()]
        if 'effects' not in entity:
            entity['effects'] = {}
        effect = {}
        effect['id'] = buff.unpack('b')
        effect['amplifier'] = buff.unpack('b')
        effect['duration'] = buff.unpack_varint()
        effect['flags'] = buff.unpack('b')
        entity['effects'][effect['id']] = effect


    def packet_downstream_remove_entity_effect(self, buff):
        entity = self.entities[buff.unpack_varint()]
        del entity['effects'][buff.unpack('b')]


    def packet_downstream_entity_equipment(self, buff):
        entity = self.entities[buff.unpack_varint()]
        if 'equipment' not in entity:
            entity['equipment'] = [{'id': -1} for _ in range(6)]
        idx = buff.unpack_varint()
        entity['equipment'][idx] = buff.unpack_slot()


    def packet_downstream_set_passengers(self, buff):
        entity = self.entities[buff.unpack_varint()]
        count = buff.unpack_varint()
        entity['passengers'] = [buff.unpack_varint() for _ in range(count)]

        if self.player['id'] in entity['passengers']:
            self.player['vehicle'] = entity['id']
        elif self.player.get('vehicle') == entity['id']:
            self.player['vehicle'] = None


    def packet_downstream_attach_entity(self, buff):
        entity = self.entities[buff.unpack('i')]
        other = buff.unpack('i')
        if other == -1:
            entity['attached'] = None
        else:
            entity['attached'] = other


    def packet_downstream_entity_properties(self, buff):
        entity = self.entities[buff.unpack_varint()]
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


    def packet_downstream_use_bed(self, buff):
        entity = self.entities[buff.unpack_varint()]
        entity['bed'] = buff.unpack_position()


    def packet_downstream_animation(self, buff):
        entity = self.entities[buff.unpack_varint()]
        animation = buff.unpack('b')
        if animation == 2:
            entity['bed'] = None

    # Player position ---------------------------------------------------------

    # TODO: forwarding
    def packet_downstream_player_position_and_look(self, buff):
        pos_look = buff.unpack('dddff')
        flags = buff.unpack('B')
        keys = ("x", "y", "z", "yaw", "pitch")

        for idx, key in enumerate(keys):
            if flags & (1 << idx):
                self.player[key] += pos_look[idx]
            else:
                self.player[key] = pos_look[idx]

        teleport_id = buff.unpack_varint()

        if not self.forwarding:
            self.upstream.send_packet(
                "teleport_confirm",
                self.bt.pack_varint(teleport_id))

        if not self.spawned:
            self.ticker.add_loop(1, self.update_player_inc)
            self.ticker.add_loop(20, self.update_player_full)
            self.spawned = True

    def packet_upstream_player(self, buff):
        self.player['on_ground'] = buff.unpack('?')

    def packet_upstream_player_position(self, buff):
        self.player['x'] = buff.unpack('d')
        self.player['y'] = buff.unpack('d')
        self.player['z'] = buff.unpack('d')
        self.player['on_ground'] = buff.unpack('?')

    def packet_upstream_player_look(self, buff):
        self.player['yaw'] = buff.unpack('f')
        self.player['pitch'] = buff.unpack('f')
        self.player['on_ground'] = buff.unpack('?')

    def packet_upstream_player_position_and_look(self, buff):
        self.player['x'] = buff.unpack('d')
        self.player['y'] = buff.unpack('d')
        self.player['z'] = buff.unpack('d')
        self.player['yaw'] = buff.unpack('f')
        self.player['pitch'] = buff.unpack('f')
        self.player['on_ground'] = buff.unpack('?')

    # Player action -----------------------------------------------------------

    def packet_upstream_entity_action(self, buff):
        entity_id = buff.unpack_varint()
        action = buff.unpack_varint()
        jump_boost = buff.unpack_varint()

        if   action == 0: self.player['actions']['sneaking'] = True
        elif action == 1: self.player['actions']['sneaking'] = False
        elif action == 2: self.player['bed'] = None
        elif action == 3: self.player['actions']['sprinting'] = True
        elif action == 4: self.player['actions']['sprinting'] = False
        elif action == 5: self.player['actions']['horse_jumping'] = True
        elif action == 6: self.player['actions']['horse_jumping'] = False
        elif action == 7: pass  # TODO: horse inventory
        elif action == 8: pass  # TODO: elytra

    # Player vehicle ----------------------------------------------------------

    def packet_downstream_vehicle_move(self, buff):
        vehicle = self.entities[self.player['vehicle']]

        self.player['x'] = vehicle['x'] = buff.unpack('d')
        self.player['y'] = vehicle['y'] = buff.unpack('d')
        self.player['z'] = vehicle['z'] = buff.unpack('d')
        self.player['yaw'] = vehicle['yaw'] = buff.unpack('f')
        self.player['pitch'] = vehicle['pitch'] = buff.unpack('f')

    def packet_upstream_vehicle_move(self, buff):
        vehicle = self.entities[self.player['vehicle']]

        self.player['x'] = vehicle['x'] = buff.unpack('d')
        self.player['y'] = vehicle['y'] = buff.unpack('d')
        self.player['z'] = vehicle['z'] = buff.unpack('d')
        self.player['yaw'] = vehicle['yaw'] = buff.unpack('f')
        self.player['pitch'] = vehicle['pitch'] = buff.unpack('f')


    # Player tasks ------------------------------------------------------------

    def update_player_inc(self):
        vehicle = self.player.get('vehicle')
        if vehicle:
            self.upstream.send_packet(
                "player_look",
                self.bt.pack(
                    'ff?',
                    self.player['yaw'],
                    self.player['pitch'],
                    self.player['on_ground']))
            self.upstream.send_packet(
                "steer_vehicle",
                self.bt.pack('ffb', 0, 0, 0))
            self.upstream.send_packet(
                "vehicle_move",
                self.bt.pack(
                    'dddff',
                    self.player['x'],
                    self.player['y'],
                    self.player['z'],
                    self.player['yaw'],
                    self.player['pitch']))
        else:
            self.upstream.send_packet(
                "player",
                self.bt.pack('?', self.player['on_ground']))

    def update_player_full(self):
        vehicle = self.player.get('vehicle')
        if vehicle:
            pass
        else:
            self.upstream.send_packet(
                "player_position_and_look",
                self.bt.pack(
                    'dddff?',
                    self.player['x'],
                    self.player['y'],
                    self.player['z'],
                    self.player['yaw'],
                    self.player['pitch'],
                    self.player['on_ground']))