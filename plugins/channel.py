from plugins import Plugin

class ChannelPlugin(Plugin):
    def setup(self):
        self.brand = "MineBNC"
        self.channels = set()

    def attach(self):
        if self.channels:
            self.downstream.send_packet(
                'plugin_message',
                self.bt.pack_string('REGISTER'),
                b"\x00".join(self.channels))

        self.downstream.send_packet(
            'plugin_message',
            self.bt.pack_string('MC|Brand'),
            self.bt.pack_string(self.brand))

    def packet_downstream_plugin_message(self, buff):
        channel = buff.unpack_string()

        if channel in ("REGISTER", "UNREGISTER"):
            channels = set(buff.read().split(b"\x00"))
            if channel == "REGISTER":
                self.channels |= channels
            else:
                self.channels -= channels

        elif channel == "MC|Brand":
            self.brand = buff.unpack_string()