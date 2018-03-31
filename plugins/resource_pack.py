from plugins import Plugin

class ResourcePackPlugin(Plugin):
    def setup(self):
        self.url = None
        self.hash = None

    def attach(self):
        if self.url:
            self.downstream.send_packet(
                'resource_pack_send',
                self.bt.pack_string(self.url),
                self.bt.pack_string(self.hash))

    def packet_downstream_resource_pack_send(self, buff):
        self.url = buff.unpack_string()
        self.hash = buff.unpack_string()