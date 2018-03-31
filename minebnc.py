import collections
import os.path

from twisted.internet import reactor, defer
from twisted.internet.protocol import ReconnectingClientFactory

from quarry.net.auth import Profile, OfflineProfile
from quarry.net.client import ClientFactory, ClientProtocol
from quarry.net.server import ServerFactory, ServerProtocol

from config import *
from plugins import plugins


# Globals ---------------------------------------------------------------------

downstream = None
upstream = None


# Server ----------------------------------------------------------------------

class Downstream(ServerProtocol):
    def setup(self):
        global downstream
        downstream = self

    def connection_made(self):
        if not upstream:
            self.close()
        elif whitelist and self.remote_addr.host not in whitelist:
            self.close()
        else:
            super(Downstream, self).connection_made()

    def packet_received(self, buff, name):
        if upstream:
            upstream.dispatch_packet(buff, name, "upstream")
        super(Downstream, self).packet_received(buff, name)

    def player_joined(self):
        super(Downstream, self).player_joined()
        if upstream:
            upstream.downstream_player_joined()

    def player_left(self):
        if upstream:
            upstream.downstream_player_left()


class DownstreamFactory(ServerFactory):
    protocol = Downstream
    max_players = 1

    online_mode = online_mode
    motd = motd
    force_protocol_version = protocol_version
    log_level = log_level


# Client ----------------------------------------------------------------------

class Upstream(ClientProtocol):
    forwarding = False

    # Callbacks ---------------------------------------------------------------

    def setup(self):
        self.plugins = []

    def connection_made(self):
        global upstream
        upstream = self

        super(Upstream, self).connection_made()

        for plugin in plugins:
            self.plugins.append(plugin(self.buff_type, self.ticker, self))

    def connection_lost(self, reason=None):
        global upstream
        upstream = None

        super(Upstream, self).connection_lost(reason)

    # Synchronization logic ---------------------------------------------------

    def downstream_player_joined(self):
        self.logger.info("Attaching...")
        self.ticker.stop()
        self.forwarding = True
        for plugin in self.plugins:
            plugin.set_downstream(downstream)
            plugin.set_forwarding(True)
            plugin.attach()
        self.logger.info("Attached!")

    def downstream_player_left(self):
        self.logger.info("Detaching...")
        for plugin in self.plugins:
            plugin.detach()
            plugin.set_forwarding(False)
            plugin.set_downstream(None)
        self.forwarding = False
        self.ticker.start()
        self.logger.info("Detached!")


    # Packet handlers ---------------------------------------------------------

    def packet_received(self, buff, name):
        self.dispatch_packet(buff, name, "downstream")
        super(Upstream, self).packet_received(buff, name)


    def dispatch_packet(self, buff, name, direction):
        buff.save()
        method_name = "packet_%s_%s" % (direction, name)
        for plugin in self.plugins:
            handler = getattr(plugin, method_name, None)
            if handler:
                try:
                    handler(buff)
                    assert len(buff) == 0, "Packet too long: %s" % method_name
                except Exception as e:
                    self.logger.exception(e)
                buff.restore()

        if self.forwarding:
            if direction == "upstream":
                endpoint = upstream
            else:
                endpoint = downstream
            endpoint.send_packet(name, buff.read())


class UpstreamFactory(ClientFactory, ReconnectingClientFactory):
    protocol = Upstream
    force_protocol_version = protocol_version
    log_level = log_level


@defer.inlineCallbacks
def run():
    cache_path = os.path.join(os.path.dirname(__file__), "cache.json")
    if os.path.exists(cache_path):
        profile = yield Profile.from_file(profiles_path=cache_path)
    elif email and password:
        profile = yield Profile.from_credentials(email, password)
        profile.to_file(profiles_path=cache_path)
    else:
        profile = yield OfflineProfile.from_display_name(username)
    downstream_factory = DownstreamFactory()
    downstream_factory.listen(listen_host, listen_port)
    upstream_factory = UpstreamFactory(profile)
    upstream_factory.connect(connect_host, connect_port)


if __name__ == "__main__":
    run()
    reactor.run()
