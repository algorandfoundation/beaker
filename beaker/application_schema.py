from algosdk.future.transaction import StateSchema
from pyteal import *
from .consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE


class DynamicApplicationStateValue:
    def __init__(
        self, stack_type: TealType, max_keys: int, key_gen: SubroutineFnWrapper = None
    ):
        self.stack_type = stack_type
        self.max_keys = max_keys

        if key_gen is not None:
            if key_gen.type_of() != TealType.bytes:
                raise Exception("key generator must evaluate to bytes")

        self.key_generator = key_gen

    def __call__(self, key_seed: Expr) -> "ApplicationStateValue":
        key = key_seed
        if self.key_generator is not None:
            key = self.key_generator(key)
        return ApplicationStateValue(stack_type=self.stack_type, key=key)

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> "ApplicationStateValue":
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)
        return ApplicationStateValue(stack_type=self.stack_type, key=key)


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
                raise Exception("key must evaluate to bytes")
            self.key = key
        else:
            self.key = None

        self.stack_type = stack_type
        self.static = static
        self.default = default
        self.descr = descr

    def has_return(self) -> bool:
        return super().has_return()

    def type_of(self) -> TealType:
        return self.stack_type

    def __teal__(self, options: "CompileOptions"):
        return self.get().__teal__(options)

    def __str__(self) -> str:
        return f"ApplicationState {self.key}"

    def str_key(self) -> str:
        return self.key.byte_str.replace('"', "")

    def set_default(self) -> Expr:
        if self.default:
            return App.globalPut(self.key, self.default)

        if self.stack_type == TealType.uint64:
            return App.globalPut(self.key, Int(0))
        else:
            return App.globalPut(self.key, Bytes(""))

    def set(self, val: Expr) -> Expr:
        if self.static:
            return Seq(
                v := App.globalGetEx(Int(0), self.key),
                Assert(Not(v.hasValue())),
                App.globalPut(self.key, val),
            )

        return App.globalPut(self.key, val)

    def increment(self, cnt: Expr = Int(1)) -> Expr:
        if self.stack_type != TealType.uint64:
            raise TealInputError("Only uint64 types can be incremented")

        return Seq(
            (sv := ScratchVar()).store(self.get()),
            self.set(sv.load() + cnt),
        )

    def decrement(self, cnt: Expr = Int(1)) -> Expr:
        if self.stack_type != TealType.uint64:
            raise TealInputError("Only uint64 types can be decremented")

        return Seq(
            (sv := ScratchVar()).store(self.get()),
            self.set(sv.load() - cnt),
        )

    def get(self) -> Expr:
        return App.globalGet(self.key)

    def get_maybe(self) -> MaybeValue:
        return App.globalGetEx(Int(0), self.key)

    def get_must(self) -> Expr:
        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        return If((v := App.globalGetEx(Int(0), self.key)).hasValue(), v.value(), val)

    def delete(self) -> Expr:
        if self.static:
            raise Exception("Cannot delete static global param")
        return App.globalDel(self.key)

    def is_default(self) -> Expr:
        return self.get() == self.default


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

    def initialize(self):
        return Seq(
            *[g.set_default() for g in self.declared_vals.values() if not g.static]
        )

    def schema(self):
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class DynamicAccountStateValue:
    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: SubroutineFnWrapper = None,
        descr: str = None,
    ):

        if max_keys <= 0 or max_keys > 16:
            raise Exception("max keys expected to be between 0 and 16")

        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr

        if key_gen is not None:
            if key_gen.type_of() != TealType.bytes:
                raise TealTypeError(key_gen.type_of(), TealType.bytes)

        self.key_generator = key_gen

    def __call__(self, key_seed: Expr) -> "AccountStateValue":
        key = key_seed
        if self.key_generator is not None:
            key = self.key_generator(key)
        return AccountStateValue(stack_type=self.stack_type, key=key)

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> "AccountStateValue":
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)
        return AccountStateValue(stack_type=self.stack_type, key=key)


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

    def has_return(self):
        return False

    def type_of(self):
        return self.stack_type

    def __teal__(self, compileOptions: CompileOptions):
        return self.get().__teal__(compileOptions)

    def __str__(self) -> str:
        return f"AccountStateValue {self.key}"

    def str_key(self) -> str:
        return self.key.byte_str.replace('"', "")

    def set(self, val: Expr, acct: Expr = Txn.sender()) -> Expr:
        if val.type_of() != self.stack_type:
            raise TealTypeError(val.type_of(), self.stack_type)

        return App.localPut(acct, self.key, val)

    def set_default(self, acct: Expr = Txn.sender()) -> Expr:
        if self.default is not None:
            return App.localPut(acct, self.key, self.default)

        if self.stack_type == TealType.uint64:
            return App.localPut(acct, self.key, Int(0))
        else:
            return App.localPut(acct, self.key, Bytes(""))

    def get(self, acct: Expr = Txn.sender()) -> Expr:
        return App.localGet(acct, self.key)

    def get_maybe(self, acct: Expr = Txn.sender()) -> MaybeValue:
        return App.localGetEx(acct, Int(0), self.key)

    def get_must(self, acct: Expr = Txn.sender()) -> Expr:
        return Seq(val := self.get_maybe(acct), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr, acct: Expr = Txn.sender()) -> Expr:
        if val.type_of() != self.stack_type:
            return TealTypeError(val.type_of(), self.stack_type)

        return Seq(
            (v := App.localGetEx(acct, Int(0), self.key)),
            If(v.hasValue(), v.value(), val),
        )

    def delete(self, acct: Expr = Txn.sender()) -> Expr:
        return App.localDel(acct, self.key)

    def is_default(self, acct: Expr = Txn.sender()) -> Expr:
        return self.get(acct) == self.default


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

    def initialize(self, acct: Expr = Txn.sender()):
        return Seq(*[l.set_default(acct) for l in self.declared_vals.values()])

    def schema(self):
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )
