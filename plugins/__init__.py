class Plugin(object):
    def __init__(self, buff_type, ticker, upstream):
        self.bt = buff_type
        self.ticker = ticker
        self.upstream = upstream
        self.downstream = None
        self.forwarding = False
        self.setup()

    def set_downstream(self, downstream):
        self.downstream = downstream

    def set_forwarding(self, forwarding):
        self.forwarding = forwarding

    def setup(self):
        pass

    def attach(self):
        pass

    def detach(self):
        pass

from plugins.abilities import AbilitiesPlugin
from plugins.boss_bar import BossBarPlugin
from plugins.channel import ChannelPlugin
from plugins.chat import ChatPlugin
from plugins.entities import EntitiesPlugin
from plugins.game import GamePlugin
from plugins.inventory import InventoryPlugin
from plugins.player_list import PlayerListPlugin
from plugins.resource_pack import ResourcePackPlugin
from plugins.stats import StatsPlugin
from plugins.time import TimePlugin
from plugins.world import WorldPlugin
from plugins.world_border import WorldBorderPlugin

plugins = [GamePlugin, ChannelPlugin, AbilitiesPlugin, InventoryPlugin,
           StatsPlugin, TimePlugin, WorldBorderPlugin, WorldPlugin,
           EntitiesPlugin, BossBarPlugin, ResourcePackPlugin, PlayerListPlugin,
           ChatPlugin]
