from abc import ABC, abstractmethod
from typing import Optional
from pyteal import BytesZero, Int, Expr, Extract, Bytes, TealTypeError

blob_page_size = 128 - 1  # need 1 byte for key
BLOB_PAGE_SIZE = Int(blob_page_size)
EMPTY_PAGE = BytesZero(BLOB_PAGE_SIZE)


class Blob(ABC):
    """
    Blob is a class holding static methods to work with the global or local storage of an application as a Binary Large OBject

    """

    def __init__(self, key_limit: int, /, *, keys: Optional[int | list[int]] = None):

        _keys: list[int] = []

        if keys is None:
            _keys = [x for x in range(key_limit)]
        elif type(keys) is int:
            _keys = [x for x in range(keys)]
        elif type(keys) is list:
            _keys = keys
        else:
            raise TealTypeError(type(keys), int | list[int])

        assert max(_keys) <= 255, "larger than 1 byte key supplied"
        assert sorted(_keys) == _keys, "keys provided are not sorted"

        self.byte_keys = [key.to_bytes(1, "big") for key in _keys]
        self.byte_key_str = Bytes("base16", b"".join(self.byte_keys).hex())

        self.int_keys = [Int(key) for key in _keys]
        self.start_key = self.int_keys[0]

        self._max_keys = len(_keys)
        self._max_bytes = self._max_keys * blob_page_size
        self._max_bits = self._max_bytes * 8

        self.max_keys = Int(self._max_keys)
        self.max_bytes = Int(self._max_bytes)

    def _key(self, i: Expr) -> Expr:
        return Extract(self.byte_key_str, i, Int(1))

    def _key_idx(self, idx: Expr) -> Expr:
        return idx / BLOB_PAGE_SIZE

    def _offset_for_idx(self, idx: Expr) -> Expr:
        return idx % BLOB_PAGE_SIZE

    @abstractmethod
    def zero(self) -> Expr:
        ...

    @abstractmethod
    def get_byte(self, idx: Int) -> Expr:
        ...

    @abstractmethod
    def set_byte(self, idx: Int, byte: Expr) -> Expr:
        ...

    @abstractmethod
    def read(self, bstart: Expr, bstop: Expr) -> Expr:
        ...

    @abstractmethod
    def write(self, bstart: Expr, buff: Expr) -> Expr:
        ...
