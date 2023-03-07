from abc import abstractmethod
from copy import copy
from typing import Literal, cast

from pyteal import (
    App,
    Assert,
    Bytes,
    CompileOptions,
    Concat,
    Expr,
    If,
    Int,
    MaybeValue,
    Not,
    Seq,
    Subroutine,
    SubroutineFnWrapper,
    TealBlock,
    TealInputError,
    TealSimpleBlock,
    TealType,
    TealTypeError,
    Txn,
)

__all__ = [
    "StateValue",
    "GlobalStateValue",
    "LocalStateValue",
    "prefix_key_gen",
    "identity_key_gen",
]

from beaker.state._abc import (
    AppSpecSchemaFragment,
    GlobalStateStorage,
    LocalStateStorage,
    StateStorage,
)


class StateValue(Expr, StateStorage):
    """Base Class for state values

    Attributes:
        stack_type: The type of the state value
            (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can
            only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: Literal[TealType.bytes, TealType.uint64],
        key: Expr | str | None = None,
        default: Expr | None = None,
        static: bool = False,  # noqa: FBT001, FBT002
        descr: str | None = None,
    ):
        super().__init__()

        if stack_type not in (TealType.bytes, TealType.uint64):
            raise ValueError(f"Invalid stack type: {stack_type}")

        self.stack_type = stack_type
        self.static = static
        self.descr = descr

        if key is not None:
            if isinstance(key, str):
                key = Bytes(key)
            elif key.type_of() != TealType.bytes:
                raise TealTypeError(key.type_of(), TealType.bytes)
        self._key = key

        if default is not None and default.type_of() != self.stack_type:
            raise TealTypeError(default.type_of(), self.stack_type)
        self.default = default

    def __set_name__(self, owner: type, name: str) -> None:
        if self._key is None:
            self._key = Bytes(name)

    @property
    def key(self) -> Expr:
        if self._key is None:
            raise TealInputError(f"{self} has no key defined")
        return self._key

    # Required methods for `Expr subclass`
    def has_return(self) -> bool:
        return False

    def type_of(self) -> TealType:
        return self.stack_type

    def __teal__(self, options: CompileOptions) -> tuple[TealBlock, TealSimpleBlock]:
        return self.get().__teal__(options)

    def __str__(self) -> str:
        return f"StateValue {self.key}"

    def str_key(self) -> str:
        """returns the string held by the key Bytes object"""
        return cast(Bytes, self.key).byte_str.replace('"', "")

    def increment(self, cnt: Expr = Int(1)) -> Expr:  # noqa: B008
        """helper to increment a counter"""
        check_is_int(self)
        check_not_static(self)

        return self.set(self.get() + cnt)

    def decrement(self, cnt: Expr = Int(1)) -> Expr:  # noqa: B008
        """helper to decrement a counter"""
        check_is_int(self)
        check_not_static(self)

        return self.set(self.get() - cnt)

    def set_default(self) -> Expr:
        """sets the default value if one is provided, if
        none provided sets the zero value for its type"""

        return self.set(_get_default_for_type(self.stack_type, self.default))

    def is_default(self) -> Expr:
        """checks to see if the value set equals the default value"""
        default = _get_default_for_type(self.stack_type, self.default)
        return self.get() == default

    def num_keys(self) -> int:
        return 1

    def value_type(self) -> Literal[TealType.bytes, TealType.uint64]:
        return self.stack_type

    def app_spec_json(self) -> AppSpecSchemaFragment:
        return AppSpecSchemaFragment(
            "declared",
            {
                "type": self.value_type().name,
                "key": self.str_key(),
                "descr": self.descr or "",
            },
        )

    @abstractmethod
    def set(self, val: Expr) -> Expr:
        """sets the value to the argument passed"""

    @abstractmethod
    def get(self) -> Expr:
        """gets the value stored for this state value"""

    @abstractmethod
    def get_maybe(self) -> MaybeValue:
        """gets a MaybeValue that can be used for existence check"""

    @abstractmethod
    def get_must(self) -> Expr:
        """gets the value stored at the key. if none is stored, Assert out of the program"""

    @abstractmethod
    def get_else(self, val: Expr) -> Expr:
        """gets the value stored at the key. if none is stored, return the value passed"""

    @abstractmethod
    def exists(self) -> Expr:
        """checks if the value is set (to whatever value. Returns Int(1) if value is set, Int(0) otherwise."""

    @abstractmethod
    def delete(self) -> Expr:
        """deletes the key from state, if the value is static it will be a compile time error"""


class GlobalStateValue(StateValue, GlobalStateStorage):
    """Allows storage of state values for an application (global state)

    Attributes:
        stack_type: The type of the state value (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def initialize(self) -> Expr | None:
        if self.static and self.default is None:
            return None
        return self.set_default()

    def __str__(self) -> str:
        return f"ApplicationStateValue {self._key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)
        if self.static:
            return Seq(
                v := App.globalGetEx(Int(0), self.key),
                Assert(Not(v.hasValue())),
                App.globalPut(self.key, val),
            )
        return App.globalPut(self.key, val)

    def get(self) -> Expr:
        return App.globalGet(self.key)

    def get_maybe(self) -> MaybeValue:
        return App.globalGetEx(Int(0), self.key)

    def get_must(self) -> Expr:
        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)
        return Seq(v := self.get_maybe(), If(v.hasValue(), v.value(), val))

    def get_external(self, app_id: Expr) -> MaybeValue:
        if app_id.type_of() is not TealType.uint64:
            raise TealTypeError(app_id, TealType.uint64)
        return App.globalGetEx(app_id, self.key)

    def exists(self) -> Expr:
        return Seq(val := self.get_maybe(), val.hasValue())

    def delete(self) -> Expr:
        check_not_static(self)
        return App.globalDel(self.key)


class LocalStateValue(StateValue, LocalStateStorage):
    """Allows storage of keyed values for an account opted into an application (local state)

    Attributes:
        stack_type: The type of the state value (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: Literal[TealType.bytes, TealType.uint64],
        key: Expr | str | None = None,
        default: Expr | None = None,
        static: bool = False,  # noqa: FBT001, FBT002
        descr: str | None = None,
    ):
        super().__init__(stack_type, key, default, static, descr)
        self._acct: Expr = Txn.sender()

    @property
    def acct(self) -> Expr:
        if self._acct is None:
            raise TealInputError(f"{self} has no account defined")
        return self._acct

    def initialize(self, acct: Expr) -> Expr | None:
        if self.static and self.default is None:
            return None
        return self[acct].set_default()

    def __str__(self) -> str:
        return f"AccountStateValue {self._acct} {self._key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.static:
            return Seq(
                v := self.get_maybe(),
                Assert(Not(v.hasValue())),
                App.localPut(self.acct, self.key, val),
            )

        return App.localPut(self.acct, self.key, val)

    def get(self) -> Expr:
        return App.localGet(self.acct, self.key)

    def get_maybe(self) -> MaybeValue:
        return App.localGetEx(self.acct, Int(0), self.key)

    def get_must(self) -> Expr:
        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)
        return Seq(v := self.get_maybe(), If(v.hasValue(), v.value(), val))

    def get_external(self, app_id: Expr) -> MaybeValue:
        if app_id.type_of() is not TealType.uint64:
            raise TealTypeError(app_id, TealType.uint64)
        return App.localGetEx(self.acct, app_id, self.key)

    def exists(self) -> Expr:
        return Seq(val := self.get_maybe(), val.hasValue())

    def delete(self) -> Expr:
        return App.localDel(self.acct, self.key)

    def __getitem__(self, acct: Expr) -> "LocalStateValue":
        asv = copy(self)
        asv._acct = acct
        return asv


def prefix_key_gen(prefix: str) -> SubroutineFnWrapper:
    @Subroutine(TealType.bytes)
    def prefix_key_gen(key_seed: Expr) -> Expr:
        return Concat(Bytes(prefix), key_seed)

    return prefix_key_gen


def identity_key_gen(key_seed: Expr) -> Expr:
    return key_seed


def check_not_static(sv: StateValue) -> None:
    if sv.static:
        raise TealInputError(f"StateValue {sv} is static")


def check_is_int(sv: StateValue) -> None:
    if sv.stack_type != TealType.uint64:
        raise TealInputError(f"StateValue {sv} is not integer type")


def check_match_type(sv: StateValue, val: Expr) -> None:
    in_type = val.type_of()
    if in_type != sv.stack_type and in_type != TealType.anytype:
        raise TealTypeError(in_type, sv.stack_type)


def _get_default_for_type(stack_type: TealType, default: Expr | None) -> Expr:
    if default is not None:
        return default

    if stack_type == TealType.bytes:
        return Bytes("")
    else:
        return Int(0)
