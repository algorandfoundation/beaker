from abc import ABC, abstractmethod
from typing import Literal

from pyteal import TealType, Expr


class StateStorage(ABC):
    @abstractmethod
    def known_keys(self) -> list[str] | list[bytes] | list[str | bytes] | None:
        ...

    @abstractmethod
    def num_keys(self) -> int:
        ...

    @abstractmethod
    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        ...

    @abstractmethod
    def description(self) -> str | None:
        ...


class ApplicationStateStorage(StateStorage):
    @abstractmethod
    def initialize(self) -> Expr | None:
        ...


class AccountStateStorage(StateStorage):
    @abstractmethod
    def initialize(self, acct: Expr) -> Expr | None:
        ...


class BoxStorage(ABC):
    pass
