from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, Literal, TypeAlias, TypeVar

from pyteal import Expr, SubroutineFnWrapper, TealType, abi
from pyteal.types import require_type

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state._abc import (
    AppSpecSchemaFragment,
    GlobalStateStorage,
    LocalStateStorage,
    StateStorage,
)
from beaker.state.primitive import (
    GlobalStateValue,
    LocalStateValue,
    StateValue,
    identity_key_gen,
    prefix_key_gen,
)

__all__ = [
    "ReservedStateValue",
    "ReservedGlobalStateValue",
    "ReservedLocalStateValue",
]


KeyGenerator: TypeAlias = SubroutineFnWrapper | Callable[[Expr], Expr]


ST = TypeVar("ST", bound=StateValue)


class ReservedStateValue(Generic[ST], StateStorage, ABC):
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
        if stack_type not in (TealType.bytes, TealType.uint64):
            raise ValueError(f"Invalid stack type: {stack_type}")
        if prefix is not None:
            if key_gen is not None:
                raise ValueError("Only one of key_gen or prefix can be specified")
            if prefix:
                key_gen = prefix_key_gen(prefix)
            else:
                key_gen = identity_key_gen
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
        if isinstance(value, SubroutineFnWrapper):
            require_type(value, TealType.bytes)
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

    def num_keys(self) -> int:
        return self.max_keys

    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        return self.stack_type

    def app_spec_json(self) -> AppSpecSchemaFragment:
        return AppSpecSchemaFragment(
            "reserved",
            {
                "type": self.value_type().name,
                "max_keys": self.num_keys(),
                "descr": self.descr or "",
            },
        )


class ReservedGlobalStateValue(
    ReservedStateValue[GlobalStateValue], GlobalStateStorage
):
    """Reserved Application State (global state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
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
        super().__init__(stack_type, max_keys, key_gen, descr, prefix=prefix)

        if max_keys <= 0 or max_keys > MAX_GLOBAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_GLOBAL_STATE}")

    def initialize(self) -> Expr | None:
        return None

    def _get_state_for_key(self, key: Expr) -> GlobalStateValue:
        """Method to access the state value with the key seed provided"""
        return GlobalStateValue(stack_type=self.stack_type, key=key, descr=self.descr)


class ReservedLocalStateValue(ReservedStateValue[LocalStateValue], LocalStateStorage):
    """Reserved Account State (local state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
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
        super().__init__(stack_type, max_keys, key_gen, descr, prefix=prefix)

        if max_keys <= 0 or max_keys > MAX_LOCAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_LOCAL_STATE}")

    def initialize(self, acct: Expr) -> Expr | None:
        return None

    def _get_state_for_key(self, key: Expr) -> LocalStateValue:
        """Access AccountState value given key_seed"""
        return LocalStateValue(stack_type=self.stack_type, key=key, descr=self.descr)
