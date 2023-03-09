from abc import ABC, abstractmethod
from typing import Literal, NamedTuple

from pyteal import Expr, TealType


class AppSpecSchemaFragment(NamedTuple):
    section: str
    data: dict


class StateStorage(ABC):
    @abstractmethod
    def app_spec_json(self) -> AppSpecSchemaFragment | None:
        ...

    @abstractmethod
    def num_keys(self) -> int:
        ...

    @abstractmethod
    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        ...


class GlobalStateStorage(StateStorage):
    @abstractmethod
    def initialize(self) -> Expr | None:
        ...


class LocalStateStorage(StateStorage):
    @abstractmethod
    def initialize(self, acct: Expr) -> Expr | None:
        ...


# class BoxStorage(ABC):
#     pass
