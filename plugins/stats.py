from plugins import Plugin

class StatsPlugin(Plugin):
    def setup(self):
        self.health = 0
        self.food = 0
        self.food_saturation = 0
        self.experience_bar = 0
        self.experience_level = 0
        self.experience_total = 0

    def attach(self):
        self.downstream.send_packet(
            'update_health',
            self.bt.pack('f', self.health),
            self.bt.pack_varint(self.food),
            self.bt.pack('f', self.food_saturation))

        self.downstream.send_packet(
            'set_experience',
            self.bt.pack('f', self.experience_bar),
            self.bt.pack_varint(self.experience_level),
            self.bt.pack_varint(self.experience_total))

    def packet_downstream_update_health(self, buff):
        self.health = buff.unpack('f')
        self.food = buff.unpack_varint()
        self.food_saturation = buff.unpack('f')

    def packet_downstream_set_experience(self, buff):
        self.experience_bar = buff.unpack('f')
        self.experience_level = buff.unpack_varint()
        self.experience_total = buff.unpack_varint()