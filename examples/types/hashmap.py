from typing import Final
import pyteal as pt

MAX_PAGE_BYTES = 1024 * 4
# MAX_PAGE_BYTES = 32


def itob(i: int) -> bytearray:
    return bytearray(i.to_bytes(8, "big"))


def btoi(b: bytearray) -> int:
    return int.from_bytes(b, "big")


class HashMap:
    def __init__(self, element_type: type[pt.abi.BaseType]):

        # Not going to take the full 2 pages
        self._pages: Final[int] = 2
        # use uint64 as key
        self._key_size: Final[int] = 8
        # we can split pages up for fewer ops, need to experiment?
        self._elements_per_bucket: Final[int] = 1

        # Figure out how the storage will break out
        self.element_value_size: Final[int] = pt.abi.size_of(element_type)
        self.element_size: Final[int] = self.element_value_size + self._key_size
        self.elements_per_page: Final[int] = MAX_PAGE_BYTES // self.element_size

        # The max number of element slots we can use
        self.num_slots: Final[int] = (self._pages * MAX_PAGE_BYTES) // self.element_size

        # Split the number slots into buckets
        # each bucket holds {_elements_per_bucket} elements
        self.buckets: Final[int] = self.num_slots // self._elements_per_bucket

        #### Mutable properties

        # pointers is a list of buckets, each bucket has a list of starting offsets
        # in our storage backing
        self.pointers: list[bytearray] = [bytearray()] * self.buckets

        # Actual storage, offsets pointed to by pointers
        self.storage: list[bytearray] = [bytearray([0] * MAX_PAGE_BYTES)] * self._pages

        # Track how much of the storage has been written to
        self.slots_occupied = 0

    def _hash(self, key: int) -> int:
        return key % self.buckets

    def _page(self, offset: int) -> int:
        return offset // MAX_PAGE_BYTES

    def _idx(self, offset: int) -> int:
        return offset % MAX_PAGE_BYTES

    def _alloc(self, val: bytearray) -> int:
        bytes_occupied = self.slots_occupied * self.element_size
        # overwrite whatever is there
        page_offset = self._idx(bytes_occupied)
        self.storage[self._page(bytes_occupied)][
            page_offset : page_offset + self.element_size
        ] = val
        # bump slots used
        self.slots_occupied += 1
        # return start index for value
        return bytes_occupied

    def put(self, key: int, val: bytearray):
        tupled_val = itob(key) + val
        bucket_key = self._hash(key)
        bucket_record_offsets = self.pointers[bucket_key]

        for offset in bucket_record_offsets:
            page = self._page(offset)
            page_offset = self._idx(offset)
            record_bytes = self.storage[page][
                page_offset : page_offset + self.element_size
            ]

            # if key matches, we found it, overwrite
            if btoi(record_bytes[0:8]) == key:
                self.storage[page][
                    page_offset : page_offset + self.element_size
                ] = tupled_val
                return

        # alloc new storage and save the offset we wrote to
        new_offset = self._alloc(tupled_val)

        # TODO:
        #  just appending should break at max elems per bucket size
        #  what do? make it a linked list?
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

    def delete(self, key: int):
        bucket_key = self._hash(key)
        bucket_record_offsets = self.pointers[bucket_key]
        for idx, offset in enumerate(bucket_record_offsets):
            page = self._page(offset)
            page_offset = self._idx(offset)
            record_bytes = self.storage[page][
                page_offset : page_offset + self.element_size
            ]

            if btoi(record_bytes[0:8]) == key:
                self.storage[page][
                    page_offset : page_offset + self.element_size
                ] = bytearray(bytes(self.element_size))

                print(f"TODO: need to remove {offset} at {idx} from buckets ")
                return

        raise KeyError(f"No key: {key}")
