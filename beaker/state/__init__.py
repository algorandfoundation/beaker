from typing import Any, Generic, TypeVar, TypeAlias

from algosdk.transaction import StateSchema
from pyteal import TealType, Expr, Seq, Txn

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state._abc import (
    ApplicationStateStorage,
    AccountStateStorage,
    StateStorage,
    AppSpecSchemaFragment,
)
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


StateDict: TypeAlias = dict[str, dict[str, dict]]


T = TypeVar("T")


def _get_attrs_of_type(namespace: Any, type_: type[T]) -> dict[str, T]:
    result = {}
    for name in dir(namespace):
        if not name.startswith("__"):
            try:
                value = getattr(namespace, name, None)
            except Exception:
                value = None
            if isinstance(value, type_):
                result[name] = value
    return result


class State(Generic[ST]):
    def __init__(self, namespace: Any, storage_class: type[ST]):
        self._fields: list[ST] = []
        self.schema = StateSchema(num_uints=0, num_byte_slices=0)
        self._app_spec_fragment: StateDict = {"declared": {}, "reserved": {}}
        for name, field in _get_attrs_of_type(namespace, storage_class).items():
            match field.value_type():
                case TealType.uint64:
                    self.schema.num_uints += field.num_keys()
                case TealType.bytes:
                    self.schema.num_byte_slices += field.num_keys()
                case _:
                    raise TypeError("Only uint64 and bytes supported")
            match field.app_spec_json():
                case AppSpecSchemaFragment(section, data):
                    self._app_spec_fragment.setdefault(section, {})[name] = data
                case None:
                    pass
                case other:
                    raise ValueError(f"Unhandled value: {other}")
            self._fields.append(field)

    def dictify(self) -> StateDict:
        """Convert the state to a dict for encoding"""
        return self._app_spec_fragment

    @property
    def total_keys(self) -> int:
        return self.schema.num_uints + self.schema.num_byte_slices


class ApplicationState(State):
    def __init__(self, namespace: Any):
        super().__init__(namespace=namespace, storage_class=ApplicationStateStorage)

        if self.total_keys > MAX_GLOBAL_STATE:
            raise ValueError(
                f"Too much application state, expected {self.total_keys} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(list(filter(None, [f.initialize() for f in self._fields])))


class AccountState(State):
    def __init__(self, namespace: Any):
        super().__init__(namespace=namespace, storage_class=AccountStateStorage)

        if self.total_keys > MAX_LOCAL_STATE:
            raise ValueError(
                f"Too much account state, expected {self.total_keys} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(list(filter(None, [f.initialize(acct=acct) for f in self._fields])))
