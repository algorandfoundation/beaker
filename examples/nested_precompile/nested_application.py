from typing import Final
from pyteal import (
    abi,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Seq,
    TealType,
    TxnField,
    TxnType,
)
from beaker import *
from beaker.precompile import AppPrecompile, LSigPrecompile


class LSig(LogicSignature):
    pass


class Child1(Application):
    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )

    @create
    def create(self):
        return Seq(
            self.initialize_application_state(),
        )

    @external
    def increment_counter(self, *, output: abi.Uint64):
        """Increment the counter global state."""
        return Seq(
            self.counter.increment(),
            output.set(self.counter.get()),
        )


class Child2(Application):
    lsig: LSigPrecompile = LSigPrecompile(LSig())

    @external(read_only=True)
    def get_lsig_addr(self, *, output: abi.Address):
        return output.set(self.lsig.logic.hash())


class Parent(Application):
    child_1: AppPrecompile = AppPrecompile(Child1())
    child_2: AppPrecompile = AppPrecompile(Child2())

    @external
    def create_child_1(self, *, output: abi.Uint64):
        """Create a new child app."""
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.child_1.approval.binary,
                    TxnField.clear_state_program: self.child_1.clear.binary,
                    TxnField.global_num_uints: Int(1),
                }
            ),
            output.set(InnerTxn.created_application_id()),
        )

    @external
    def create_child_2(self, *, output: abi.Uint64):
        """Create a new child app."""
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.child_2.approval.binary,
                    TxnField.clear_state_program: self.child_2.clear.binary,
                    TxnField.global_num_uints: Int(1),
                }
            ),
            output.set(InnerTxn.created_application_id()),
        )


class Grandparent(Application):
    parent: AppPrecompile = AppPrecompile(Parent())

    @external
    def create_parent(self, *, output: abi.Uint64):
        """Create a new parent app."""
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.parent.approval.binary,
                    TxnField.clear_state_program: self.parent.clear.binary,
                }
            ),
            output.set(InnerTxn.created_application_id()),
        )
