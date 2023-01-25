from typing import Final
import pyteal as pt

MAX_PAGE_BYTES = 1024 * 4


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
        self._elements_per_bucket: Final[int] = 8

        # Figure out how the storage will break out
        self.element_value_size: Final[int] = pt.abi.size_of(element_type)
        self.element_size: Final[int] = self.element_value_size + self._key_size
        self.elements_per_page: Final[int] = MAX_PAGE_BYTES // self.element_size

        # The max number of element slots we can use
        self.max_slots: Final[int] = self.elements_per_page * self._pages

        # Split the number slots into buckets
        # each bucket holds {_elements_per_bucket} elements
        self.num_buckets: Final[int] = self.max_slots // self._elements_per_bucket

        #### Mutable properties #####

        # Track how much of the storage has been written to
        self.slots_occupied = 0

        # each bucket has a list of starting offsets that act as pointers
        # into our storage backing
        self.buckets: list[bytearray] = [bytearray([]) for _ in range(self.num_buckets)]

        # Actual storage, offsets stored in buckets as pointers
        self.storage: list[bytearray] = [
            bytearray([0] * MAX_PAGE_BYTES) for _ in range(self._pages)
        ]

    def _hash(self, key: int) -> int:
        return key % self.num_buckets

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

        # TODO: We cant go over the number of slots available
        # in our storage backing without doing something
        # like adding more pages
        assert self.slots_occupied <= self.max_slots

        # return start index for value
        return bytes_occupied

    def put(self, key: int, val: bytearray):
        tupled_val = itob(key) + val
        bucket_key = self._hash(key)
        bucket_record_offsets = self.buckets[bucket_key]

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
        print(f"Writing to bucket: {bucket_key} with offset {new_offset}")
        self.buckets[bucket_key] += itob(new_offset)

    def get(self, key: int) -> bytearray:
        bucket_key = self._hash(key)
        bucket_record_offsets = self.buckets[bucket_key]
        print(f"Getting key: {key} (bucket: {bucket_key})")

        for idx in range(0, len(bucket_record_offsets) // 8):
            offset = btoi(bucket_record_offsets[idx * 8 : (idx + 1) * 8])

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
        bucket_record_offsets = self.buckets[bucket_key]
        for idx in range(0, len(bucket_record_offsets) // 8):
            offset = btoi(bucket_record_offsets[idx * 8 : (idx + 1) * 8])

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

    def print_debug(self):
        print(f"Slots used: {self.slots_occupied}")
        print(f"Max Slots: {self.max_slots}")
        print(f"Num buckets: {len(self.buckets)}")

        for bucket_idx, bucket in enumerate(self.buckets):
            print(f"Bucket {bucket_idx}")
            for idx in range(0, len(bucket) // 8):
                offset = btoi(bucket[idx * 8 : (idx + 1) * 8])
                print(f"\t {idx} => {offset}")
