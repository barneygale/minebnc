from plugins import Plugin

class AbilitiesPlugin(Plugin):
    def setup(self):
        self.invulnerable = False
        self.flying = False
        self.allow_flying = False
        self.creative_mode = False
        self.flying_speed = 0
        self.fov_modifier = 0

    def attach(self):
        self.downstream.send_packet(
            'player_abilities',
            self.bt.pack(
                'Bff',
                self.invulnerable  << 0 |
                self.flying        << 1 |
                self.allow_flying  << 2 |
                self.creative_mode << 3,
                self.flying_speed,
                self.fov_modifier))

    def packet_downstream_player_abilities(self, buff):
        flags = buff.unpack('B')
        self.invulnerable = bool(flags & 1)
        self.flying = bool(flags & 2)
        self.allow_flying = bool(flags & 4)
        self.creative_mode = bool(flags & 8)
        self.flying_speed = buff.unpack('f')
        self.fov_modifier = buff.unpack('f')

    def packet_upstream_player_abilities(self, buff):
        flags = buff.unpack('B')
        self.invulnerable  = bool(flags & 1)
        self.flying        = bool(flags & 2)
        self.allow_flying  = bool(flags & 4)
        self.creative_mode = bool(flags & 8)
        self.flying_speed  = buff.unpack('f')
        self.fov_modifier  = buff.unpack('f')