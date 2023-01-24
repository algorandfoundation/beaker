import pyteal as pt

MAX_PAGE_BYTES = 32


def itob(i: int) -> bytearray:
    return bytearray(i.to_bytes(8, "big"))


def btoi(b: bytearray) -> int:
    return int.from_bytes(b, "big")


class HashMap:
    def __init__(self, element_type: type[pt.abi.BaseType]):

        self.key_size = 8  # uint64 bytes
        self.element_value_size = pt.abi.size_of(element_type)
        self.element_size = self.element_value_size + self.key_size

        self.elements_per_page = MAX_PAGE_BYTES // self.element_size

        # Not going to take the full 2 pages
        self.pages = 2

        # Actual storage, offsets pointed to by pointers
        self.storage: list[bytearray] = [bytearray([0] * MAX_PAGE_BYTES)] * self.pages

        # we can split pages up for fewer ops,
        # need to experiment?
        self.elements_per_bucket = 1
        self.buckets = (
            self.pages
            * MAX_PAGE_BYTES
            // (self.elements_per_bucket * self.element_size)
        )

        # pointers is a list of buckets, each bucket has a list of starting offsets in our storage backing
        self.pointers: list[bytearray] = [bytearray()] * self.buckets

        self.slots_occupied = 0

    def _hash(self, key: int) -> int:
        return key % self.buckets

    # def _some_hash(self, key: int)->int:
    #    # n should be large prime??
    #    self.a = 1000
    #    self.b = 10000000
    #    self.n = 7919
    #    return (self.a*key + self.b) % self.n

    # def _some_other_hash(self, key: int)->int:
    #    self.n = 7919
    #    return self.z * key // self.n

    def _page(self, offset: int) -> int:
        return offset // MAX_PAGE_BYTES

    def _idx(self, offset: int) -> int:
        return offset % MAX_PAGE_BYTES

    def _alloc(self, val: bytearray) -> int:
        bytes_occupied = self.slots_occupied * self.element_size
        page_offset = self._idx(bytes_occupied)
        self.storage[self._page(bytes_occupied)][
            page_offset : page_offset + self.element_size
        ] = val
        self.slots_occupied += 1
        return bytes_occupied

    def put(self, key: int, val: bytearray):
        tupled_val = itob(key) + val

        bucket_key = self._hash(key)
        bucket_record_offsets = self.pointers[bucket_key]

        # TODO: skip if all 0s?
        for offset in bucket_record_offsets:
            page = self._page(offset)
            page_offset = self._idx(offset)
            record_bytes = self.storage[page][
                page_offset : page_offset + self.element_size
            ]
            if btoi(record_bytes[0:8]) == key:
                print("matching key")
                self.storage[page][page_offset:] = tupled_val
                # no need to update the bucket
                return

        new_offset = self._alloc(tupled_val)
        self.pointers[bucket_key] += itob(new_offset)

    def get(self, key: int) -> bytearray:
        bucket_key = self._hash(key)
        bucket_record_offsets = self.pointers[bucket_key]

        for offset in bucket_record_offsets:
            page = self._page(offset)
            page_offset = self._idx(offset)
            record_bytes = self.storage[page][
                page_offset : page_offset + self.element_size
            ]
            if btoi(record_bytes[0:8]) == key:
                return record_bytes[8:]

        raise KeyError(f"No key: {key}")


if __name__ == "__main__":
    hm = HashMap(pt.abi.Uint64)
    val = 123
    hm.put(10, itob(val))
    got = btoi(hm.get(10))
    assert val == got
