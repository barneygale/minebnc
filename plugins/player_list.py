from plugins import Plugin

class PlayerListPlugin(Plugin):
    def setup(self):
        self.players = {}
        self.players_header_footer = None

    def attach(self):
        # Send 'Player List Header and Footer'
        if self.players_header_footer:
            self.downstream.send_packet(
                'player_list_header_footer',
                self.bt.pack_chat(self.players_header_footer[0]),
                self.bt.pack_chat(self.players_header_footer[1]))

        # Send 'Player List Item'
        data = b""
        for player in self.players.values():
            data += self.bt.pack_uuid(player['uuid'])
            data += self.bt.pack_string(player['name'])
            data += self.bt.pack_varint(len(player['properties']))
            for property in player['properties']:
                data += self.bt.pack_string(property['name'])
                data += self.bt.pack_string(property['value'])
                data += self.bt.pack_optional(self.bt.pack_string, property['signature'])
            data += self.bt.pack_varint(player['game_mode'])
            data += self.bt.pack_varint(player['ping'])
            data += self.bt.pack_optional(self.bt.pack_chat, player['display_name'])

        self.downstream.send_packet(
            'player_list_item',
            self.bt.pack_varint(0),
            self.bt.pack_varint(len(self.players)),
            data)

    def packet_downstream_player_list_item(self, buff):
        action = buff.unpack_varint()
        for _ in range(buff.unpack_varint()):
            uuid = buff.unpack_uuid()

            # Delete entry
            if action == 4:
                if uuid in self.players:
                    del self.players[uuid]
                continue

            # Update entry
            elif uuid in self.players:
                player = self.players[uuid]

            # Create entry
            elif action == 0:
                player = self.players[uuid] = {'uuid': uuid}

            # Invalid data from server
            else:
                player = {}

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


    def packet_downstream_player_list_header_footer(self, buff):
        self.players_header_footer = buff.unpack_chat(), buff.unpack_chat()