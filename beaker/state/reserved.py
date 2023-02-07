from abc import ABC, abstractmethod
from typing import Callable, TypeAlias, TypeVar, Generic, Literal

from pyteal import TealType, SubroutineFnWrapper, TealTypeError, Expr
from pyteal.ast import abi

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state._abc import ApplicationStateStorage, AccountStateStorage
from beaker.state.primitive import (
    StateValue,
    ApplicationStateValue,
    AccountStateValue,
    prefix_key_gen,
)

__all__ = [
    "ReservedStateValue",
    "ReservedApplicationStateValue",
    "ReservedAccountStateValue",
]


KeyGenerator: TypeAlias = SubroutineFnWrapper | Callable[[Expr], Expr]


ST = TypeVar("ST", bound=StateValue)


class ReservedStateValue(Generic[ST], ABC):
    """Base Class for ReservedStateValues

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (subroutine): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients

    """

    def __init__(
        self,
        stack_type: Literal[TealType.bytes, TealType.uint64],
        max_keys: int,
        key_gen: KeyGenerator | None = None,
        descr: str | None = None,
        *,
        prefix: str | None = None,
    ):
        if prefix is not None:
            if key_gen is not None:
                raise ValueError("Only one of key_gen or prefix can be specified")
            key_gen = prefix_key_gen(prefix)
        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr
        self.key_gen = key_gen

    def __set_name__(self, owner: type, name: str) -> None:
        if self.key_gen is None:
            self.key_gen = prefix_key_gen(name)

    @property
    def key_gen(self) -> KeyGenerator | None:
        return self._key_gen

    @key_gen.setter
    def key_gen(self, value: KeyGenerator) -> None:
        if isinstance(value, SubroutineFnWrapper) and value.type_of() != TealType.bytes:
            raise TealTypeError(value.type_of(), TealType.bytes)
        self._key_gen = value

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> ST:
        """Method to access the state value with the key seed provided"""
        key: Expr
        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()
        else:
            key = key_seed

        if self.key_gen is not None:
            key = self.key_gen(key)
        return self._get_state_for_key(key)

    @abstractmethod
    def _get_state_for_key(self, key: Expr) -> ST:
        ...


class ReservedApplicationStateValue(
    ReservedStateValue[ApplicationStateValue], ApplicationStateStorage
):
    """Reserved Application State (global state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients
    """

    def initialize(self) -> Expr | None:
        return None

    def known_keys(self) -> list[str] | list[bytes] | list[str | bytes] | None:
        return None

    def num_keys(self) -> int:
        return self.max_keys

    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        return self.stack_type

    def description(self) -> str | None:
        return self.descr

    def __init__(
        self,
        stack_type: Literal[TealType.bytes, TealType.uint64],
        max_keys: int,
        key_gen: KeyGenerator | None = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_GLOBAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_GLOBAL_STATE}")

    def _get_state_for_key(self, key: Expr) -> ApplicationStateValue:
        """Method to access the state value with the key seed provided"""
        return ApplicationStateValue(
            stack_type=self.stack_type, key=key, descr=self.descr
        )


class ReservedAccountStateValue(
    ReservedStateValue[AccountStateValue], AccountStateStorage
):
    """Reserved Account State (local state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients
    """

    def initialize(self, acct: Expr) -> Expr | None:
        return None

    def known_keys(self) -> list[str] | list[bytes] | list[str | bytes] | None:
        return None

    def num_keys(self) -> int:
        return self.max_keys

    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        return self.stack_type

    def description(self) -> str | None:
        return self.descr

    def __init__(
        self,
        stack_type: Literal[TealType.bytes, TealType.uint64],
        max_keys: int,
        key_gen: KeyGenerator | None = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_LOCAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_LOCAL_STATE}")

    def _get_state_for_key(self, key: Expr) -> AccountStateValue:
        """Access AccountState value given key_seed"""
        return AccountStateValue(stack_type=self.stack_type, key=key, descr=self.descr)
