from plugins import Plugin


class BossBarPlugin(Plugin):
    def setup(self):
        self.boss_bars = {}

    def attach(self):
        for boss_bar in self.boss_bars.values():
            self.downstream.send_packet(
                'boss_bar',
                self.bt.pack_uuid(boss_bar['uuid']),
                self.bt.pack_varint(0),
                self.bt.pack_chat(boss_bar['title']),
                self.bt.pack('f', boss_bar['health']),
                self.bt.pack_varint(boss_bar['color']),
                self.bt.pack_varint(boss_bar['dividers']),
                self.bt.pack('B', boss_bar['flags']))

    def packet_downstream_boss_bar(self, buff):
        uuid = buff.unpack_uuid()
        action = buff.unpack_varint()
        if action == 0:
            # Create boss bar
            self.boss_bars[uuid] = {'uuid': uuid}
        elif action == 1:
            del self.boss_bars[uuid]
            return

        boss_bar = self.boss_bars[uuid]

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
