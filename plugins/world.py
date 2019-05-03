from quarry.types.chunk import BlockArray, LightArray
from plugins import Plugin


class WorldPlugin(Plugin):
    def setup(self):
        self.chunks = {}
        self.dimension = 0

    def set_block(self, x, y, z, block_id):
        cx, bx = divmod(x, 16)
        cy, by = divmod(y, 16)
        cz, bz = divmod(z, 16)

        chunk = self.chunks.get((cx, cz))
        if chunk:
            chunk['sections'][cy][0][by*256 + bz*16 + bx] = block_id

        # TODO: adjust lighting

    def get_block(self, x, y, z):
        cx, bx = divmod(x, 16)
        cy, by = divmod(y, 16)
        cz, bz = divmod(z, 16)

        chunk = self.chunks.get((cx, cz))
        if chunk:
            return chunk['sections'][cy][0][by*256 + bz*16 + bx]
        else:
            return 0

    def attach(self):
        for coords, chunk in self.chunks.items():
            x, z = coords

            bitmask = 0
            data = b""
            for i, section in enumerate(chunk['sections']):
                if not section[0].is_empty():
                    bitmask |= 1 << i
                    data += self.bt.pack_chunk_section(*section)
            data += self.bt.pack('I'*256, *chunk['biomes'])

            self.downstream.send_packet(
                'chunk_data',
                self.bt.pack('ii?', x, z, True),
                self.bt.pack_varint(bitmask),
                self.bt.pack_varint(len(data)),
                data,
                self.bt.pack_varint(len(chunk['block_entities'])),
                *[self.bt.pack_nbt(entity)
                  for entity in chunk['block_entities'].values()])

            for coords, action in chunk['block_actions'].items():
                x, y, z = coords
                block_id, action_id, action_value = action

                if block_id == (self.get_block(x, y, z) >> 4):
                    self.downstream.send_packet(
                        'block_action',
                        self.bt.pack_position(x, y, z),
                        self.bt.pack('BB', action_id, action_value),
                        self.bt.pack_varint(block_id))

    def packet_downstream_join_game(self, buff):
        self.dimension = buff.unpack('ibi')[2]
        buff.discard()

    def packet_downstream_respawn(self, buff):
        self.dimension = buff.unpack('i')
        buff.discard()

    def packet_downstream_chunk_data(self, buff):
        x, z, contiguous = buff.unpack('ii?')
        bitmask = buff.unpack_varint()
        size = buff.unpack_varint()

        if contiguous:
            chunk = self.chunks[x, z] = {
                'sections': [None] * 16,
                'block_entities': {},
                'block_actions': {}}
        else:
            chunk = self.chunks[x, z]

        for idx in range(16):
            if bitmask & (1 << idx):
                section = buff.unpack_chunk_section(
                    self.dimension == 0)
            elif self.dimension == 0:
                section = (BlockArray.empty(buff.registry),
                           LightArray.empty(),
                           LightArray.empty())
            else:
                section = (BlockArray.empty(buff.registry),
                           LightArray.empty())

            chunk['sections'][idx] = section

        if contiguous:
            chunk['biomes'] = buff.unpack('I' * 256)

        for _ in range(buff.unpack_varint()):
            block_entity = buff.unpack_nbt()
            block_entity_obj = block_entity.to_obj()[""]
            chunk['block_entities'][
                block_entity_obj['x'],
                block_entity_obj['y'],
                block_entity_obj['z']] = block_entity

    def packet_downstream_unload_chunk(self, buff):
        x, z = buff.unpack('ii')
        if (x, z) in self.chunks:
            del self.chunks[x, z]

    def packet_downstream_block_change(self, buff):
        x, y, z = buff.unpack_position()
        block = buff.registry.decode_block(buff.unpack_varint())
        self.set_block(x, y, z, block)

    def packet_downstream_multi_block_change(self, buff):
        chunk_x, chunk_z = buff.unpack('ii')
        for _ in range(buff.unpack_varint()):
            block_xz, block_y = buff.unpack('BB')
            block = buff.registry.decode_block(buff.unpack_varint())
            self.set_block(
                16 * chunk_x + block_xz >> 4,
                block_y,
                16 * chunk_z + block_xz & 0x0F,
                block)

    def packet_downstream_explosion(self, buff):
        x, y, z, radius = buff.unpack('ffff')
        for _ in range(buff.unpack('i')):
            dx, dy, dz = buff.unpack('bbb')
            self.set_block(x + dx, y + dy, z + dz, 0)
        px, py, pz = buff.unpack('fff')

    def packet_downstream_update_block_entity(self, buff):
        x, y, z = buff.unpack_position()
        action = buff.unpack('B')
        new_tag = buff.unpack_nbt()

        chunk_x, chunk_z = x // 16, z // 16
        block_entities = self.chunks[chunk_x, chunk_z][
            'block_entities']
        old_tag = block_entities.get((x, y, z))

        if old_tag and not new_tag:
            del block_entities[x, y, z]
        elif not old_tag and new_tag:
            block_entities[x, y, z] = new_tag
        elif old_tag and new_tag:
            old_tag.update(new_tag)

    def packet_downstream_block_action(self, buff):
        x, y, z = buff.unpack_position()
        action_id, action_value = buff.unpack('BB')
        block_id = buff.unpack_varint()

        if block_id == (self.get_block(x, y, z) >> 4):
            chunk_x, chunk_z = x // 16, z // 16
            self.chunks[chunk_x, chunk_z]['block_actions'][x, y, z] = (
                (block_id, action_id, action_value))