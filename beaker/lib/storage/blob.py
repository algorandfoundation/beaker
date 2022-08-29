from abc import ABC, abstractmethod
from pyteal import BytesZero, Int, Expr, Extract, Bytes

blob_page_size = 128 - 1  # need 1 byte for key
BLOB_PAGE_SIZE = Int(blob_page_size)
EMPTY_PAGE = BytesZero(BLOB_PAGE_SIZE)


class Blob(ABC):
    """
    Blob is a class holding static methods to work with the global storage of an application as a binary large object

    """

    def __init__(
        self, key_limit: int, /, *, max_keys: int = None, keys: list[int] = None
    ):
        assert not (
            max_keys is not None and keys is not None
        ), "cant supply both max_keys and keys"

        if keys is None:
            if max_keys is not None:
                keys = [x for x in range(max_keys)]
            else:
                keys = [x for x in range(key_limit)]

        assert max(keys) <= 255, "larger than 1 byte key supplied"
        assert sorted(keys) == keys, "keys provided are not sorted"

        self.byte_keys = [key.to_bytes(1, "big") for key in keys]
        self.byte_key_str = Bytes("base16", b"".join(self.byte_keys).hex())

        self.int_keys = [Int(key) for key in keys]
        self.start_key = self.int_keys[0]

        self._max_keys = len(keys)
        self._max_bytes = self._max_keys * blob_page_size
        self._max_bits = self._max_bytes * 8

        self.max_keys = Int(self._max_keys)
        self.max_bytes = Int(self._max_bytes)

    def _key(self, i) -> Expr:
        return Extract(self.byte_key_str, i, Int(1))

    def _key_idx(self, idx: Int) -> Expr:
        return idx / BLOB_PAGE_SIZE

    def _offset_for_idx(self, idx: Int) -> Expr:
        return idx % BLOB_PAGE_SIZE

    @abstractmethod
    def zero(self) -> Expr:
        ...

    @abstractmethod
    def get_byte(self, idx) -> Expr:
        ...

    @abstractmethod
    def set_byte(self, idx, byte) -> Expr:
        ...

    @abstractmethod
    def read(self, bstart, bstop) -> Expr:
        ...

    @abstractmethod
    def write(self, bstart, buff) -> Expr:
        ...
