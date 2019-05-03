from plugins import Plugin


class GamePlugin(Plugin):
    def setup(self):
        self.player_id = 0
        self.game_mode = 0
        self.dimension = 0
        self.difficulty = 0
        self.max_players = 0
        self.level_type = "DEFAULT"
        self.reduced_debug_info = False
        self.spawn_position = (0, 0, 0)
        self.raining = False
        self.tags = {}
        self.recipes = []
        self.commands = {}

    def attach(self):
        self.downstream.send_packet(
            'join_game',
            self.bt.pack(
                'ibibb',
                self.player_id,
                self.game_mode,
                self.dimension,
                self.difficulty,
                self.max_players),
            self.bt.pack_string(self.level_type),
            self.bt.pack('?', self.reduced_debug_info))

        self.downstream.send_packet(
            'spawn_position',
            self.bt.pack_position(*self.spawn_position))

        if self.raining:
            self.downstream.send_packet(
                'change_game_state',
                self.bt.pack('bf', 2, 0))

        data = b""
        for kind in ('block', 'item', 'fluid'):
            data += self.bt.pack_varint(len(self.tags[kind]))
            for tag, values in self.tags[kind].items():
                data += self.bt.pack_string(tag)
                data += self.bt.pack_varint(len(values))
                for value in values:
                    data += self.bt.pack_varint(value)
        self.downstream.send_packet('tags', data)

        data = self.bt.pack_varint(len(self.recipes))
        for recipe in self.recipes:
            data += self.bt.pack_recipe(**recipe)
        self.downstream.send_packet('declare_recipes', data)

        self.downstream.send_packet(
            'declare_commands',
            self.bt.pack_commands(self.commands))

    def packet_downstream_join_game(self, buff):
        self.player_id = buff.unpack('i')
        self.game_mode = buff.unpack('b')
        self.dimension = buff.unpack('i')
        self.difficulty = buff.unpack('b')
        self.max_players = buff.unpack('b')
        self.level_type = buff.unpack_string()
        self.reduced_debug_info = buff.unpack('?')

    def packet_downstream_respawn(self, buff):
        self.dimension = buff.unpack('i')
        self.difficulty = buff.unpack('b')
        self.game_mode = buff.unpack('b')
        self.level_type = buff.unpack_string()

    def packet_downstream_server_difficulty(self, buff):
        self.difficulty = buff.unpack('b')

    def packet_downstream_change_game_state(self, buff):
        reason, value = buff.unpack('bf')
        if reason == 1:
            self.raining = False
        elif reason == 2:
            self.raining = True
        elif reason == 3:
            self.game_mode = int(value)

    def packet_downstream_spawn_position(self, buff):
        self.spawn_position = buff.unpack_position()

    def packet_downstream_keep_alive(self, buff):
        id = buff.unpack('q')
        if not self.forwarding:
            self.upstream.send_packet("keep_alive", self.bt.pack('q', id))

    def packet_downstream_tags(self, buff):
        for kind in ('block', 'item', 'fluid'):
            self.tags[kind] = {}
            for _ in range(buff.unpack_varint()):
                tag = buff.unpack_string()
                self.tags[kind][tag] = []
                for __ in range(buff.unpack_varint()):
                    self.tags[kind][tag].append(buff.unpack_varint())

    def packet_downstream_declare_recipes(self, buff):
        self.recipes = []
        for _ in range(buff.unpack_varint()):
            self.recipes.append(buff.unpack_recipe())

    def packet_downstream_declare_commands(self, buff):
        self.commands = buff.unpack_commands()
