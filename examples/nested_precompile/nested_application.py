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
    Expr,
    Approve,
)
from beaker import (
    ApplicationStateValue,
    Application,
    LogicSignature,
    precompiled,
    this_app,
)


class PutFilesHere(Application):
    pass


class Child1(Application):
    counter = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )


child1_app = Child1(implement_default_create=False)


@child1_app.create
def create() -> Expr:
    return Seq(
        this_app().initialize_application_state(),
    )


@child1_app.external
def increment_counter(*, output: abi.Uint64) -> Expr:
    """Increment the counter global state."""
    return Seq(
        child1_app.counter.increment(),
        output.set(child1_app.counter.get()),
    )


child2_app = PutFilesHere(name="Child2")
lsig = LogicSignature(Approve())


@child2_app.external(read_only=True)
def get_lsig_addr(*, output: abi.Address) -> Expr:
    lsig_pc = precompiled(lsig)
    return output.set(lsig_pc.logic.address())


parent_app = PutFilesHere(name="Parent")


@parent_app.external
def create_child_1(*, output: abi.Uint64) -> Expr:
    """Create a new child app."""
    child_1_pc = precompiled(child1_app)
    return Seq(
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.approval_program: child_1_pc.approval.binary,
                TxnField.clear_state_program: child_1_pc.clear.binary,
                TxnField.global_num_uints: Int(1),
            }
        ),
        output.set(InnerTxn.created_application_id()),
    )


@parent_app.external
def create_child_2(*, output: abi.Uint64) -> Expr:
    """Create a new child app."""
    child_2_pc = precompiled(child2_app)
    return Seq(
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.approval_program: child_2_pc.approval.binary,
                TxnField.clear_state_program: child_2_pc.clear.binary,
                TxnField.global_num_uints: Int(1),
            }
        ),
        output.set(InnerTxn.created_application_id()),
    )


grand_parent_app = PutFilesHere(name="Grandparent")


@grand_parent_app.external
def create_parent(*, output: abi.Uint64) -> Expr:
    """Create a new parent app."""
    parent_app_pc = precompiled(parent_app)
    return Seq(
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.approval_program: parent_app_pc.approval.binary,
                TxnField.clear_state_program: parent_app_pc.clear.binary,
            }
        ),
        output.set(InnerTxn.created_application_id()),
    )
