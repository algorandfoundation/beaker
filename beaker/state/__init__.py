from inspect import getattr_static
from typing import Any, Generic, TypeVar

from algosdk.future.transaction import StateSchema
from pyteal import TealType, Expr, Seq, Txn

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state._abc import ApplicationStateStorage, AccountStateStorage, StateStorage
from beaker.state.blob import StateBlob, ApplicationStateBlob, AccountStateBlob
from beaker.state.primitive import (
    StateValue,
    ApplicationStateValue,
    AccountStateValue,
    prefix_key_gen,
    identity_key_gen,
)
from beaker.state.reserved import (
    ReservedStateValue,
    ReservedApplicationStateValue,
    ReservedAccountStateValue,
)

ST = TypeVar("ST", bound=StateStorage)


class State(Generic[ST]):
    def __init__(self, klass: type, storage_klass: type[ST]):
        fields: dict[str, ST] = {}
        for name in dir(klass):
            if not name.startswith("__"):
                value = getattr_static(klass, name, None)
                if isinstance(value, storage_klass):
                    fields[name] = value

        self.fields = fields
        self.__dict__.update(fields)

        self.num_uints = sum(
            f.num_keys() for f in fields.values() if f.value_type() == TealType.uint64
        )

        self.num_byte_slices = sum(
            f.num_keys() for f in fields.values() if f.value_type() == TealType.bytes
        )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """Convert the state to a dict for encoding"""
        return {
            "declared": {
                name: {
                    "type": _stack_type_to_string(field.value_type()),
                    "key": keys[0],
                    "descr": field.description() or "",
                }
                for name, field in self.fields.items()
                if (keys := field.known_keys()) is not None and len(keys) == 1  # HACK!
            },
            "reserved": {
                name: {
                    "type": _stack_type_to_string(field.value_type()),
                    "max_keys": field.num_keys(),
                    "descr": field.description() or "",
                }
                for name, field in self.fields.items()
                if (keys := field.known_keys()) is not None and len(keys) > 1  # HACK!
            },
        }

    def schema(self) -> StateSchema:
        """gets the schema as num uints/bytes for app create transactions"""
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class ApplicationState(State):
    def __init__(self, klass: type):
        super().__init__(klass=klass, storage_klass=ApplicationStateStorage)
        if (total := self.num_uints + self.num_byte_slices) > MAX_GLOBAL_STATE:
            raise ValueError(
                f"Too much application state, expected {total} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(list(filter(None, [f.initialize() for f in self.fields.values()])))


class AccountState(State):
    def __init__(self, klass: type):
        super().__init__(klass=klass, storage_klass=AccountStateStorage)

        if (total := self.num_uints + self.num_byte_slices) > MAX_LOCAL_STATE:
            raise ValueError(
                f"Too much account state, expected {total} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            list(filter(None, [f.initialize(acct=acct) for f in self.fields.values()]))
        )


def _stack_type_to_string(st: TealType) -> str:
    if st in (TealType.uint64, TealType.bytes):
        return st.name

    raise Exception("Only uint64 and bytes supported")
