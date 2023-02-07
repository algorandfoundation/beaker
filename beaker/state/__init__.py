from inspect import getattr_static
from typing import Any, Generic, TypeVar, Literal, TypedDict

from algosdk.transaction import StateSchema
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


class DeclaredStateDict(TypedDict):
    type: str
    key: str | bytes
    descr: str


class ReservedStateDict(TypedDict):
    type: str
    max_keys: int
    descr: str


class StateDict(TypedDict):
    declared: dict[str, DeclaredStateDict]
    reserved: dict[str, ReservedStateDict]


class State(Generic[ST]):
    def __init__(self, klass: type, storage_klass: type[ST]):
        self.fields: dict[str, ST] = {}
        self.schema = StateSchema(num_uints=0, num_byte_slices=0)
        for name in dir(klass):
            if not name.startswith("__"):
                value = getattr_static(klass, name, None)
                if isinstance(value, storage_klass):
                    match value.value_type():
                        case TealType.uint64:
                            self.schema.num_uints += value.num_keys()
                        case TealType.bytes:
                            self.schema.num_byte_slices += value.num_keys()
                        case _:
                            raise TypeError("Only uint64 and bytes supported")

                    self.fields[name] = value

    def dictify(self) -> StateDict:
        """Convert the state to a dict for encoding"""
        return {
            "declared": {
                name: {
                    "type": field.value_type().name,
                    "key": field.known_keys()[0],  # type: ignore[index]
                    "descr": field.description() or "",
                }
                for name, field in self.fields.items()
                if field.known_keys() is not None and field.num_keys() == 1  # HACK!
            },
            "reserved": {
                name: {
                    "type": field.value_type().name,
                    "max_keys": field.num_keys(),
                    "descr": field.description() or "",
                }
                for name, field in self.fields.items()
                if field.known_keys() is None  # HACK!
            },
        }

    @property
    def total_keys(self) -> int:
        return self.schema.num_uints + self.schema.num_byte_slices


class ApplicationState(State):
    def __init__(self, klass: type):
        super().__init__(klass=klass, storage_klass=ApplicationStateStorage)

        if self.total_keys > MAX_GLOBAL_STATE:
            raise ValueError(
                f"Too much application state, expected {self.total_keys} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(list(filter(None, [f.initialize() for f in self.fields.values()])))


class AccountState(State):
    def __init__(self, klass: type):
        super().__init__(klass=klass, storage_klass=AccountStateStorage)

        if self.total_keys > MAX_LOCAL_STATE:
            raise ValueError(
                f"Too much account state, expected {self.total_keys} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            list(filter(None, [f.initialize(acct=acct) for f in self.fields.values()]))
        )
