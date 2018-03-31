from plugins import Plugin


class WorldBorderPlugin(Plugin):
    def setup(self):
        self.x = 0
        self.z = 0
        self.old_diameter = 0
        self.new_diameter = 0
        self.speed = 0
        self.portal_teleport_boundary = 0
        self.warning_time = 0
        self.warning_blocks = 0

    def attach(self):
        self.downstream.send_packet(
            'world_border',
            self.bt.pack_varint(3),
            self.bt.pack(
                'dddd',
                self.x,
                self.z,
                self.old_diameter,
                self.new_diameter),
            self.bt.pack_varint(self.speed, max_bits=64),
            self.bt.pack_varint(self.portal_teleport_boundary),
            self.bt.pack_varint(self.warning_time),
            self.bt.pack_varint(self.warning_blocks))

    def packet_downstream_world_border(self, buff):
        action = buff.unpack_varint()
        if action == 0:
            _ = buff.unpack('d')
        elif action == 1:
            self.old_diameter = buff.unpack('d')
            self.new_diameter = buff.unpack('d')
            self.speed = buff.unpack_varint()
        elif action == 2:
            self.x = buff.unpack('d')
            self.z = buff.unpack('d')
        elif action == 3:
            self.x = buff.unpack('d')
            self.z = buff.unpack('d')
            self.old_diameter = buff.unpack('d')
            self.new_diameter = buff.unpack('d')
            self.speed = buff.unpack_varint()
            self.portal_teleport_boundary = buff.unpack_varint()
            self.warning_time = buff.unpack_varint()
            self.warning_blocks = buff.unpack_varint()
        elif action == 4:
            self.warning_time = buff.unpack_varint()
        elif action == 5:
            self.warning_blocks = buff.unpack_varint()
