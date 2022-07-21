from typing import cast, Any
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


def stack_type_to_string(st: TealType):
    if st == TealType.uint64:
        return "uint64"
    if st == TealType.bytes:
        return "bytes"
    else:
        raise Exception("Only uint64 and bytes supported")


class ApplicationStateValue(Expr):
    def __init__(
        self,
        stack_type: TealType,
        key: Expr = None,
        default: Expr = None,
        static: bool = False,
        descr: str = None,
    ):
        super().__init__()

        if key is not None:
            if key.type_of() != TealType.bytes:
                raise TealTypeError(key.type_of(), TealType.bytes)
            self.key = key
        else:
            self.key = None

        self.stack_type = stack_type
        self.static = static
        self.default = default
        self.descr = descr

    # Required methods for `Expr subclass`
    def has_return(self) -> bool:
        return False

    def type_of(self) -> TealType:
        return self.stack_type

    def __teal__(self, options: "CompileOptions"):
        return self.get().__teal__(options)

    def __str__(self) -> str:
        return f"ApplicationStateValue {self.key}"

    def str_key(self) -> str:
        """returns the string held by the key Bytes object"""
        return cast(Bytes, self.key).byte_str.replace('"', "")

    def set_default(self) -> Expr:
        """sets the default value if one is provided, if none provided sets the zero value for its type"""
        if self.default:
            return App.globalPut(self.key, self.default)

        if self.stack_type == TealType.uint64:
            return App.globalPut(self.key, Int(0))
        else:
            return App.globalPut(self.key, Bytes(""))

    def set(self, val: Expr) -> Expr:
        """sets the value to the argument passed"""
        if val.type_of() != self.stack_type:
            raise TealTypeError(val.type_of(), self.stack_type)

        if self.static:
            return Seq(
                v := App.globalGetEx(Int(0), self.key),
                Assert(Not(v.hasValue())),
                App.globalPut(self.key, val),
            )

        return App.globalPut(self.key, val)

    def increment(self, cnt: Expr = Int(1)) -> Expr:
        """helper to increment a counter"""
        if self.stack_type != TealType.uint64:
            raise TealInputError("Only uint64 types can be incremented")

        if self.static:
            raise TealInputError("Cannot increment a static value")

        return self.set(self.get() + cnt)

    def decrement(self, cnt: Expr = Int(1)) -> Expr:
        """helper to decrement a counter"""
        if self.stack_type != TealType.uint64:
            raise TealInputError("Only uint64 types can be decremented")

        if self.static:
            raise TealInputError("Cannot decrement a static value")

        return self.set(self.get() - cnt)

    def get(self) -> Expr:
        """gets the value stored for this state value"""
        return App.globalGet(self.key)

    def get_maybe(self) -> MaybeValue:
        """gets a MaybeValue that can be used for existence check"""
        return App.globalGetEx(Int(0), self.key)

    def get_must(self) -> Expr:
        """gets the value stored at the key. if none is stored, Assert out of the program"""
        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        """gets the value stored at the key. if none is stored, return the value passed"""
        return If((v := App.globalGetEx(Int(0), self.key)).hasValue(), v.value(), val)

    def delete(self) -> Expr:
        """deletes the key from state, if the value is static it will be a compile time error"""
        if self.static:
            raise TealInputError("Cannot delete static global param")
        return App.globalDel(self.key)

    def is_default(self) -> Expr:
        """checks to see if the value set equals the default value"""
        return self.get() == self.default


class DynamicApplicationStateValue:
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

        if max_keys <= 0 or max_keys > MAX_GLOBAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_GLOBAL_STATE}")

        if key_gen is not None:
            if key_gen.type_of() != TealType.bytes:
                raise TealTypeError(key_gen.type_of(), TealType.bytes)

        self.key_generator = key_gen

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> ApplicationStateValue:
        """Method to access the state value with the key seed provided"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)
        return ApplicationStateValue(
            stack_type=self.stack_type, key=key, descr=self.descr
        )


class ApplicationState:
    def __init__(
        self,
        fields: dict[str, ApplicationStateValue | DynamicApplicationStateValue] = {},
    ):

        self.declared_vals: dict[str, ApplicationStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, ApplicationStateValue)
        }

        self.__dict__.update(self.declared_vals)

        self.dynamic_vals: dict[str, DynamicApplicationStateValue] = {
            k: v
            for k, v in fields.items()
            if isinstance(v, DynamicApplicationStateValue)
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

        if (total := self.num_uints + self.num_byte_slices) > MAX_GLOBAL_STATE:
            raise Exception(
                f"Too much application state, expected {total} <= {MAX_GLOBAL_STATE}"
            )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """Convert the Application state to a dict for encoding"""
        return {
            "declared": {
                k: {"type": stack_type_to_string(v.stack_type), "key": v.str_key()}
                for k, v in self.declared_vals.items()
            },
            "dynamic": {
                k: {"type": stack_type_to_string(v.stack_type), "max-keys": v.max_keys}
                for k, v in self.dynamic_vals.items()
            },
        }

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                g.set_default()
                for g in self.declared_vals.values()
                if not g.static or (g.static and g.default is not None)
            ]
        )

    def schema(self) -> StateSchema:
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class AccountStateValue(Expr):
    def __init__(
        self,
        stack_type: TealType,
        key: Expr = None,
        default: Expr = None,
        descr: str = None,
    ):
        self.stack_type = stack_type
        self.descr = descr

        if key is not None and key.type_of() != TealType.bytes:
            raise TealTypeError(key.type_of(), TealType.bytes)

        self.key = key

        if default is not None and default.type_of() != self.stack_type:
            raise TealTypeError(default.type_of(), self.stack_type)

        self.default = default

    # Required methods for `Expr` subclass

    def has_return(self):
        return False

    def type_of(self):
        return self.stack_type

    def __teal__(self, compileOptions: CompileOptions):
        return self.get().__teal__(compileOptions)

    def __str__(self) -> str:
        return f"AccountStateValue {self.key}"

    def str_key(self) -> str:
        """returns the string held by the key Bytes object"""
        if self.key is None:
            return ""
        return cast(Bytes, self.key).byte_str.replace('"', "")

    def set_default(self, acct: Expr = Txn.sender()) -> Expr:
        """sets the default value if one is provided, if none provided sets the zero value for its type"""
        if self.default is not None:
            return App.localPut(acct, self.key, self.default)

        if self.stack_type == TealType.uint64:
            return App.localPut(acct, self.key, Int(0))
        else:
            return App.localPut(acct, self.key, Bytes(""))

    def set(self, val: Expr, acct: Expr = Txn.sender()) -> Expr:
        """sets the value to the argument passed"""
        if val.type_of() != self.stack_type:
            raise TealTypeError(val.type_of(), self.stack_type)

        return App.localPut(acct, self.key, val)

    def get(self, acct: Expr = Txn.sender()) -> Expr:
        """gets the value stored for this state value"""
        return App.localGet(acct, self.key)

    def get_maybe(self, acct: Expr = Txn.sender()) -> MaybeValue:
        """gets a MaybeValue that can be used for existence check"""
        return App.localGetEx(acct, Int(0), self.key)

    def get_must(self, acct: Expr = Txn.sender()) -> Expr:
        """gets the value stored at the key. if none is stored, Assert out of the program"""
        return Seq(val := self.get_maybe(acct), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr, acct: Expr = Txn.sender()) -> Expr:
        """gets the value stored at the key. if none is stored, return the value passed"""
        if val.type_of() != self.stack_type:
            return TealTypeError(val.type_of(), self.stack_type)

        return If(
            (v := App.localGetEx(acct, Int(0), self.key)).hasValue(), v.value(), val
        )

    def delete(self, acct: Expr = Txn.sender()) -> Expr:
        """deletes the key from state, if the value is static it will be a compile time error"""
        return App.localDel(acct, self.key)

    def is_default(self, acct: Expr = Txn.sender()) -> Expr:
        """checks to see if the value set equals the default value"""
        return self.get(acct) == self.default


class DynamicAccountStateValue:
    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: SubroutineFnWrapper = None,
        descr: str = None,
    ):

        if max_keys <= 0 or max_keys > MAX_LOCAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_LOCAL_STATE}")

        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr

        if key_gen is not None:
            if key_gen.type_of() != TealType.bytes:
                raise TealTypeError(key_gen.type_of(), TealType.bytes)

        self.key_generator = key_gen

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> AccountStateValue:
        """Access AccountState value given key_seed"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)
        return AccountStateValue(stack_type=self.stack_type, key=key)


class AccountState:
    def __init__(self, fields: dict[str, AccountStateValue | DynamicAccountStateValue]):
        self.declared_vals: dict[str, AccountStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, AccountStateValue)
        }
        self.__dict__.update(self.declared_vals)

        self.dynamic_vals: dict[str, DynamicAccountStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, DynamicAccountStateValue)
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

        if (total := self.num_uints + self.num_byte_slices) > MAX_LOCAL_STATE:
            raise Exception(
                f"Too much account state, expected {total} <= {MAX_LOCAL_STATE}"
            )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """return AccountState as a dictionary for encoding"""
        return {
            "declared": {
                k: {"type": stack_type_to_string(v.stack_type), "key": v.str_key()}
                for k, v in self.declared_vals.items()
            },
            "dynamic": {
                k: {"type": stack_type_to_string(v.stack_type), "max-keys": v.max_keys}
                for k, v in self.dynamic_vals.items()
            },
        }

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression to initialize account state fields to default values"""
        return Seq(*[l.set_default(acct) for l in self.declared_vals.values()])

    def schema(self) -> StateSchema:
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )
