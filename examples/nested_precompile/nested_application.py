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
)
from beaker.blueprints import unconditional_create_approval


class Child1State:
    counter = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )


child1_app = Application("Child1", state_class=Child1State).implement(
    unconditional_create_approval, initialize_app_state=True
)


@child1_app.external
def increment_counter(*, output: abi.Uint64) -> Expr:
    """Increment the counter global state."""
    return Seq(
        Child1State.counter.increment(),
        output.set(Child1State.counter.get()),
    )


child2_app = Application("Child2").implement(unconditional_create_approval)
lsig = LogicSignature(Approve())


@child2_app.external(read_only=True)
def get_lsig_addr(*, output: abi.Address) -> Expr:
    lsig_pc = precompiled(lsig)
    return output.set(lsig_pc.address())


parent_app = Application("Parent").implement(unconditional_create_approval)


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


grand_parent_app = Application("Grandparent").implement(unconditional_create_approval)


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
