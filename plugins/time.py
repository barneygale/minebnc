from plugins import Plugin


class TimePlugin(Plugin):
    def setup(self):
        self.time_world = 0
        self.time_day = 0

    def attach(self):
        self.downstream.send_packet(
            'time_update',
            self.bt.pack('q', self.time_world),
            self.bt.pack('q', self.time_day))

    def packet_downstream_time_update(self, buff):
        self.time_world = buff.unpack('q')
        self.time_day = buff.unpack('q')
