from abc import ABC, abstractmethod
from typing import Optional, Callable, cast

from pyteal import TealType, SubroutineFnWrapper, TealTypeError, Expr
from pyteal.ast import abi

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state.primitive import StateValue, ApplicationStateValue, AccountStateValue

__all__ = [
    "ReservedStateValue",
    "ReservedApplicationStateValue",
    "ReservedAccountStateValue",
]


class ReservedStateValue(ABC):
    """Base Class for ReservedStateValues

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (subroutine): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients

    """

    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr
        self.key_generator: Optional[SubroutineFnWrapper | Callable] = None

        if key_gen is not None:
            self.set_key_gen(key_gen)

    def set_key_gen(self, key_gen: SubroutineFnWrapper | Callable) -> None:
        if (
            isinstance(key_gen, SubroutineFnWrapper)
            and key_gen.type_of() != TealType.bytes
        ):
            raise TealTypeError(key_gen.type_of(), TealType.bytes)
        self.key_generator = key_gen

    @abstractmethod
    def __getitem__(self, key_seed: Expr | abi.BaseType) -> StateValue:
        """Method to access the state value with the key seed provided"""


class ReservedApplicationStateValue(ReservedStateValue):
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
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_GLOBAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_GLOBAL_STATE}")

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> ApplicationStateValue:
        """Method to access the state value with the key seed provided"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        key = cast(Expr, key)

        if self.key_generator is not None:
            key = self.key_generator(key)

        return ApplicationStateValue(
            stack_type=self.stack_type, key=key, descr=self.descr
        )


class ReservedAccountStateValue(ReservedStateValue):
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
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_LOCAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_LOCAL_STATE}")

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> AccountStateValue:
        """Access AccountState value given key_seed"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)

        return AccountStateValue(stack_type=self.stack_type, key=cast(Expr, key))
