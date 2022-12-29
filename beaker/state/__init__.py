from typing import Mapping, Any, cast

from algosdk.future.transaction import StateSchema
from pyteal import TealType, Expr, Seq, Txn

from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
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


class State:
    """holds all the declared and reserved state values for this storage type"""

    def __init__(
        self, fields: Mapping[str, StateValue | ReservedStateValue | StateBlob]
    ):
        self.declared_vals: dict[str, StateValue] = {
            k: v for k, v in fields.items() if isinstance(v, StateValue)
        }
        self.__dict__.update(self.declared_vals)

        self.blob_vals: dict[str, StateBlob] = {
            k: v for k, v in fields.items() if isinstance(v, StateBlob)
        }
        self.__dict__.update(self.blob_vals)

        self.reserved_vals: dict[str, ReservedStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, ReservedStateValue)
        }
        self.__dict__.update(self.reserved_vals)

        self.num_uints = len(
            [l for l in self.declared_vals.values() if l.stack_type == TealType.uint64]
        ) + sum(
            [
                l.max_keys
                for l in self.reserved_vals.values()
                if l.stack_type == TealType.uint64
            ]
        )

        self.num_byte_slices = (
            len(
                [
                    l
                    for l in self.declared_vals.values()
                    if l.stack_type == TealType.bytes
                ]
            )
            + sum(
                [
                    l.max_keys
                    for l in self.reserved_vals.values()
                    if l.stack_type == TealType.bytes
                ]
            )
            + sum([b.num_keys for b in self.blob_vals.values()])
        )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """Convert the state to a dict for encoding"""
        return {
            "declared": {
                k: {
                    "type": _stack_type_to_string(v.stack_type),
                    "key": v.str_key(),
                    "descr": v.descr if v.descr is not None else "",
                }
                for k, v in self.declared_vals.items()
            },
            "reserved": {
                k: {
                    "type": _stack_type_to_string(v.stack_type),
                    "max_keys": v.max_keys,
                    "descr": v.descr if v.descr is not None else "",
                }
                for k, v in self.reserved_vals.items()
            },
        }

    def schema(self) -> StateSchema:
        """gets the schema as num uints/bytes for app create transactions"""
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class ApplicationState(State):
    def __init__(
        self,
        fields: Mapping[
            str,
            ApplicationStateValue
            | ReservedApplicationStateValue
            | ApplicationStateBlob,
        ],
    ):
        super().__init__(fields)
        if (total := self.num_uints + self.num_byte_slices) > MAX_GLOBAL_STATE:
            raise Exception(
                f"Too much application state, expected {total} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                v.set_default()
                for v in self.declared_vals.values()
                if not v.static or (v.static and v.default is not None)
            ]
            + [v.initialize() for v in self.blob_vals.values()]
        )


class AccountState(State):
    def __init__(
        self,
        fields: Mapping[
            str, AccountStateValue | ReservedAccountStateValue | AccountStateBlob
        ],
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
            + [v.initialize() for v in self.blob_vals.values()]
        )


def _stack_type_to_string(st: TealType) -> str:
    if st in (TealType.uint64, TealType.bytes):
        return st.name

    raise Exception("Only uint64 and bytes supported")
