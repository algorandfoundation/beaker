from abc import ABC, abstractmethod
from copy import copy
from typing import Optional

from pyteal import Expr, Txn

from beaker.lib.storage import LocalBlob, GlobalBlob

__all__ = [
    "StateBlob",
    "AccountStateBlob",
    "ApplicationStateBlob",
]


class StateBlob(ABC):
    def __init__(self, num_keys: int):
        self.num_keys = num_keys

    @abstractmethod
    def initialize(self) -> Expr:
        ...

    @abstractmethod
    def read(self, start: Expr, stop: Expr) -> Expr:
        """
        Reads some bytes from the buffer

        Args:
            start: An ``Expr`` that represents the start index to read from. Should evaluate to ``uint64``.
            stop: An ``Expr`` that represents the stop index to read until. Should evaluate to ``uint64``.
        Returns:
            The bytes read from the blob from start to stop
        """
        ...

    @abstractmethod
    def write(self, start: Expr, buff: Expr) -> Expr:
        """
        Writes the buffer to the blob

        Args:
            start: An ``Expr`` that represents where to start writing. Should evaluate to ``uint64``.
            buff: An ``Expr`` that represents the bytes to write. Should evaluate to ``bytes``.

        """
        ...

    @abstractmethod
    def read_byte(self, idx: Expr) -> Expr:
        """
        Reads a single byte from the given index

        Args:
            idx: An ``Expr`` that represents the index into the blob to read the byte from. Should evaluate to ``uint64``.

        Returns:
            A single byte as a ``uint64``

        """
        ...

    @abstractmethod
    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        """
        Writes a single byte to the given index

        Args:
            idx: An ``Expr`` that represents the index to write the byte to. Should evaluate to ``uint64``.
            byte: An ``Expr`` That represents the index to write the byte to. Should evaluate to ``uint64``.

        """
        ...


class AccountStateBlob(StateBlob):
    def __init__(self, keys: Optional[int | list[int]] = None):
        self.blob = LocalBlob(keys=keys)
        self.acct: Expr = Txn.sender()

        super().__init__(self.blob._max_keys)

    def __getitem__(self, acct: Expr) -> "AccountStateBlob":
        asv = copy(self)
        asv.acct = acct
        return asv

    def initialize(self) -> Expr:
        return self.blob.zero(acct=self.acct)

    def write(self, start: Expr, buff: Expr) -> Expr:
        return self.blob.write(start, buff, acct=self.acct)

    def read(self, start: Expr, stop: Expr) -> Expr:
        return self.blob.read(start, stop, acct=self.acct)

    def read_byte(self, idx: Expr) -> Expr:
        return self.blob.get_byte(idx, acct=self.acct)

    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        return self.blob.set_byte(idx, byte, acct=self.acct)


class ApplicationStateBlob(StateBlob):
    def __init__(self, keys: Optional[int | list[int]] = None):
        self.blob = GlobalBlob(keys=keys)
        super().__init__(self.blob._max_keys)

    def initialize(self) -> Expr:
        return self.blob.zero()

    def write(self, start: Expr, buff: Expr) -> Expr:
        return self.blob.write(start, buff)

    def read(self, start: Expr, stop: Expr) -> Expr:
        return self.blob.read(start, stop)

    def read_byte(self, idx: Expr) -> Expr:
        return self.blob.get_byte(idx)

    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        return self.blob.set_byte(idx, byte)
