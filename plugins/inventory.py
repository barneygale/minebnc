from plugins import Plugin


class InventoryPlugin(Plugin):
    def setup(self):
        self.inventory = [{'id': -1} for _ in range(46)]
        self.held_item = 0
        self.recipes = set()

    def attach(self):
        self.downstream.send_packet(
            'window_items',
            self.bt.pack('Bh', 0, len(self.inventory)),
            *[self.bt.pack_slot(**item)
              for item in self.inventory])

        self.downstream.send_packet(
            'held_item_change',
            self.bt.pack('B', self.held_item))

        self.downstream.send_packet(
            'unlock_recipes',
            self.bt.pack_varint(0),
            self.bt.pack('??', False, False),
            self.bt.pack_varint(len(self.recipes)),
            b"".join(self.bt.pack_varint(recipe_id)
                     for recipe_id in self.recipes),
            self.bt.pack_varint(0))

    def packet_downstream_window_items(self, buff):
        window_id, count = buff.unpack('bh')
        slots = [buff.unpack_slot() for _ in range(count)]
        if window_id == 0:
            self.inventory[:] = slots

    def packet_downstream_set_slot(self, buff):
        window_id, idx = buff.unpack('bh')
        slot = buff.unpack_slot()
        if window_id == 0:
            self.inventory[idx] = slot

    def packet_downstream_held_item_change(self, buff):
        self.held_item = buff.unpack('B')

    def packet_upstream_held_item_change(self, buff):
        self.held_item = buff.unpack('h')

    def packet_downstream_unlock_recipes(self, buff):
        action = buff.unpack_varint()
        crafting_book_open, filtering_craftable = buff.unpack('??')

        if action == 0:
            for _ in range(buff.unpack_varint()):
                self.recipes.add(buff.unpack_varint())
            for _ in range(buff.unpack_varint()):
                self.recipes.add(buff.unpack_varint())
        elif action == 1:
            for _ in range(buff.unpack_varint()):
                self.recipes.add(buff.unpack_varint())
        elif action == 2:
            for _ in range(buff.unpack_varint()):
                self.recipes.remove(buff.unpack_varint())
