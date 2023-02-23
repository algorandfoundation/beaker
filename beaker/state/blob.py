from abc import ABC, abstractmethod
from copy import copy
from typing import Literal

from pyteal import Expr, TealType, Txn

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.lib.storage import GlobalBlob, LocalBlob

__all__ = [
    "StateBlob",
    "LocalStateBlob",
    "GlobalStateBlob",
]

from beaker.state._abc import GlobalStateStorage, LocalStateStorage, StateStorage


class StateBlob(StateStorage, ABC):
    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        return TealType.bytes

    def app_spec_json(self) -> None:
        return None

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


class LocalStateBlob(LocalStateStorage, StateBlob):
    def __init__(
        self, keys: int | list[int] = MAX_LOCAL_STATE, descr: str | None = None
    ):
        self.blob = LocalBlob(keys=keys)
        self.acct: Expr = Txn.sender()
        self.descr = descr

    def num_keys(self) -> int:
        return self.blob._max_keys

    def initialize(self, acct: Expr) -> Expr:
        return self.blob.zero(acct=acct)

    def __getitem__(self, acct: Expr) -> "LocalStateBlob":
        asv = copy(self)
        asv.acct = acct
        return asv

    def write(self, start: Expr, buff: Expr) -> Expr:
        return self.blob.write(start, buff, acct=self.acct)

    def read(self, start: Expr, stop: Expr) -> Expr:
        return self.blob.read(start, stop, acct=self.acct)

    def read_byte(self, idx: Expr) -> Expr:
        return self.blob.get_byte(idx, acct=self.acct)

    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        return self.blob.set_byte(idx, byte, acct=self.acct)


class GlobalStateBlob(GlobalStateStorage, StateBlob):
    def __init__(
        self, keys: int | list[int] = MAX_GLOBAL_STATE, descr: str | None = None
    ):
        self.blob = GlobalBlob(keys=keys)
        self.descr = descr

    def num_keys(self) -> int:
        return self.blob._max_keys

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
