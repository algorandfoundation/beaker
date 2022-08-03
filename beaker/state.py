from abc import abstractmethod, ABC
from copy import copy
from typing import Mapping, cast, Any
from algosdk.future.transaction import StateSchema
from pyteal import (
    abi,
    SubroutineFnWrapper,
    TealType,
    TealTypeError,
    Expr,
    CompileOptions,
    App,
    Bytes,
    Int,
    TealInputError,
    Assert,
    Not,
    MaybeValue,
    Txn,
    Seq,
    If,
)
from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE


def get_default_for_type(stack_type, default):
    if default is not None:
        return default

    if stack_type == TealType.bytes:
        return Bytes("")
    else:
        return Int(0)


class StateValue(Expr):
    def __init__(
        self,
        stack_type: TealType,
        key: Expr = None,
        default: Expr = None,
        static: bool = False,
        descr: str = None,
    ):
        super().__init__()

        self.stack_type = stack_type
        self.static = static
        self.descr = descr

        if key is not None and key.type_of() != TealType.bytes:
            raise TealTypeError(key.type_of(), TealType.bytes)
        self.key = key

        if default is not None and default.type_of() != self.stack_type:
            raise TealTypeError(default.type_of(), self.stack_type)
        self.default = default

    # Required methods for `Expr subclass`
    def has_return(self) -> bool:
        return False

    def type_of(self) -> TealType:
        return self.stack_type

    def __teal__(self, options: "CompileOptions"):
        return self.get().__teal__(options)

    def __str__(self) -> str:
        return f"StateValue {self.key}"

    def str_key(self) -> str:
        """returns the string held by the key Bytes object"""
        return cast(Bytes, self.key).byte_str.replace('"', "")

    def __iadd__(self, other) -> Expr:
        return self.increment(other)

    def __isub__(self, other) -> Expr:
        return self.decrement(other)

    def increment(self, cnt: Expr = Int(1)) -> Expr:
        """helper to increment a counter"""
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        check_is_int(self)
        check_not_static(self)

        return self.set(self.get() + cnt)

    def decrement(self, cnt: Expr = Int(1)) -> Expr:
        """helper to decrement a counter"""
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")
        check_is_int(self)
        check_not_static(self)
        return self.set(self.get() - cnt)

    def set_default(self) -> Expr:
        """sets the default value if one is provided, if none provided sets the zero value for its type"""
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")
        return self.set(get_default_for_type(self.stack_type, self.default))

    def is_default(self) -> Expr:
        """checks to see if the value set equals the default value"""
        default = get_default_for_type(self.stack_type, self.default)
        return self.get() == default

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
    def delete(self) -> Expr:
        """deletes the key from state, if the value is static it will be a compile time error"""


class DynamicStateValue(ABC):
    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: SubroutineFnWrapper = None,
        descr: str = None,
    ):
        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr

        if key_gen is not None and key_gen.type_of() != TealType.bytes:
            raise TealTypeError(key_gen.type_of(), TealType.bytes)

        self.key_generator = key_gen

    @abstractmethod
    def __getitem__(self, key_seed: Expr | abi.BaseType) -> StateValue:
        """Method to access the state value with the key seed provided"""


class ApplicationStateValue(StateValue):
    def __str__(self) -> str:
        return f"ApplicationStateValue {self.key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        if self.static:
            return Seq(
                v := App.globalGetEx(Int(0), self.key),
                Assert(Not(v.hasValue())),
                App.globalPut(self.key, val),
            )

        return App.globalPut(self.key, val)

    def increment(self, cnt: Expr = Int(1)) -> Expr:
        check_is_int(self)
        check_not_static(self)

        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return self.set(self.get() + cnt)

    def get(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return App.globalGet(self.key)

    def get_maybe(self) -> MaybeValue:
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return App.globalGetEx(Int(0), self.key)

    def get_must(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return If((v := App.globalGetEx(Int(0), self.key)).hasValue(), v.value(), val)

    def delete(self) -> Expr:
        check_not_static(self)

        if self.key is None:
            raise TealInputError(f"StateValue {self} has no key defined")

        return App.globalDel(self.key)


class DynamicApplicationStateValue(DynamicStateValue):
    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: SubroutineFnWrapper = None,
        descr: str = None,
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


class AccountStateValue(StateValue):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acct = Txn.sender()

    def __str__(self) -> str:
        return f"AccountStateValue {self.acct} {self.key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        if self.static:
            return Seq(
                v := self.get_maybe(),
                Assert(Not(v.hasValue())),
                App.localPut(self.acct, self.key, val),
            )

        return App.localPut(self.acct, self.key, val)

    def get(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localGet(self.acct, self.key)

    def get_maybe(self) -> MaybeValue:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localGetEx(self.acct, Int(0), self.key)

    def get_must(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return If(
            (v := App.localGetEx(self.acct, Int(0), self.key)).hasValue(),
            v.value(),
            val,
        )

    def delete(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localDel(self.acct, self.key)

    def __getitem__(self, acct: Expr):
        asv = copy(self)
        asv.acct = acct
        return asv


class DynamicAccountStateValue(DynamicStateValue):
    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: SubroutineFnWrapper = None,
        descr: str = None,
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


def stack_type_to_string(st: TealType):
    if st == TealType.uint64:
        return "uint64"
    if st == TealType.bytes:
        return "bytes"
    else:
        raise Exception("Only uint64 and bytes supported")


def check_not_static(sv: StateValue):
    if sv.static:
        raise TealInputError(f"StateValue {sv} is static")


def check_is_int(sv: StateValue):
    if sv.stack_type != TealType.uint64:
        raise TealInputError(f"StateValue {sv} is not integer type")


def check_match_type(sv: StateValue, val: Expr):
    in_type = val.type_of()
    if in_type != sv.stack_type and in_type != TealType.anytype:
        raise TealTypeError(in_type, sv.stack_type)


class State:
    """holds all the declared and dynamic state values for this storage type"""

    def __init__(self, fields: Mapping[str, StateValue | DynamicStateValue]):
        self.declared_vals: dict[str, StateValue] = {
            k: v for k, v in fields.items() if isinstance(v, StateValue)
        }

        self.__dict__.update(self.declared_vals)

        self.dynamic_vals: dict[str, DynamicStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, DynamicStateValue)
        }
        self.__dict__.update(self.dynamic_vals)

        self.num_uints = len(
            [l for l in self.declared_vals.values() if l.stack_type == TealType.uint64]
        ) + sum(
            [
                l.max_keys
                for l in self.dynamic_vals.values()
                if l.stack_type == TealType.uint64
            ]
        )

        self.num_byte_slices = len(
            [l for l in self.declared_vals.values() if l.stack_type == TealType.bytes]
        ) + sum(
            [
                l.max_keys
                for l in self.dynamic_vals.values()
                if l.stack_type == TealType.bytes
            ]
        )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """Convert the state to a dict for encoding"""
        return {
            "declared": {
                k: {
                    "type": stack_type_to_string(v.stack_type),
                    "key": v.str_key(),
                    "descr": v.descr,
                }
                for k, v in self.declared_vals.items()
            },
            "dynamic": {
                k: {
                    "type": stack_type_to_string(v.stack_type),
                    "max-keys": v.max_keys,
                    "descr": v.descr,
                }
                for k, v in self.dynamic_vals.items()
            },
        }

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                v.set_default()
                for v in self.declared_vals.values()
                if not v.static or (v.static and v.default is not None)
            ]
        )

    def schema(self) -> StateSchema:
        """gets the schema as num uints/bytes for app create transactions"""
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class ApplicationState(State):
    def __init__(
        self,
        fields: Mapping[str, ApplicationStateValue | DynamicApplicationStateValue] = {},
    ):
        super().__init__(fields)
        if (total := self.num_uints + self.num_byte_slices) > MAX_GLOBAL_STATE:
            raise Exception(
                f"Too much application state, expected {total} <= {MAX_GLOBAL_STATE}"
            )


class AccountState(State):
    def __init__(
        self, fields: Mapping[str, AccountStateValue | DynamicAccountStateValue]
    ):
        super().__init__(fields)
        if (total := self.num_uints + self.num_byte_slices) > MAX_LOCAL_STATE:
            raise Exception(
                f"Too much account state, expected {total} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                cast(AccountStateValue, v)[acct].set_default()
                for v in self.declared_vals.values()
                if not v.static or (v.static and v.default is not None)
            ]
        )
