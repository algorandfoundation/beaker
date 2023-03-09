from abc import ABC, abstractmethod
from collections.abc import Iterable

from pyteal import Bytes, BytesZero, Expr, Extract, Int

blob_page_size = 128 - 1  # need 1 byte for key
BLOB_PAGE_SIZE = Int(blob_page_size)
EMPTY_PAGE = BytesZero(BLOB_PAGE_SIZE)
_MAX_KEY = 255


class Blob(ABC):
    """
    Blob is a class holding static methods to work with the global or local storage of an application as a Binary Large OBject

    """

    def __init__(self, keys: int | Iterable[int]):
        _keys: list[int] = []

        if isinstance(keys, int):
            _keys = list(range(keys))
        else:
            _keys = sorted(keys)

        if not _keys:
            raise ValueError("keys sequence must not be empty")
        elif _keys[0] < 0:
            raise ValueError("key values must be non-negative")
        elif _keys[-1] > _MAX_KEY:
            raise ValueError("larger than 1 byte key supplied")

        self.byte_keys = [key.to_bytes(1, "big") for key in _keys]
        self.byte_key_str = Bytes("base16", b"".join(self.byte_keys).hex())

        self._max_keys = len(_keys)
        self._max_bytes = self._max_keys * blob_page_size
        self._max_bits = self._max_bytes * 8

        self.max_keys = Int(self._max_keys)
        self.max_bytes = Int(self._max_bytes)

    def _key(self, i: Expr) -> Expr:
        return Extract(self.byte_key_str, i, Int(1))

    @staticmethod
    def _key_idx(idx: Expr) -> Expr:
        return idx / BLOB_PAGE_SIZE

    @staticmethod
    def _offset_for_idx(idx: Expr) -> Expr:
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
