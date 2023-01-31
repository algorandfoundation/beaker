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


class LSig(LogicSignature):
    pass


class Child1(Application):
    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )


child1_app = Child1(implement_default_create=False)


@child1_app.create
def create() -> Expr:
    assert this_app() is child1_app
    return Seq(
        this_app().initialize_application_state(),
    )


@child1_app.external
def increment_counter(*, output: abi.Uint64) -> Expr:
    """Increment the counter global state."""
    assert this_app() is child1_app
    return Seq(
        child1_app.counter.increment(),
        output.set(child1_app.counter.get()),
    )


class Child2(Application):
    pass


child2_app = Child2()
lsig = LSig()


@child2_app.external(read_only=True)
def get_lsig_addr(*, output: abi.Address) -> Expr:
    assert this_app() is child2_app
    lsig_pc = precompiled(lsig)
    return output.set(lsig_pc.logic.hash())


class Parent(Application):
    pass


parent_app = Parent()


@parent_app.external
def create_child_1(*, output: abi.Uint64) -> Expr:
    """Create a new child app."""

    child_1_pc = precompiled(child1_app)
    assert this_app() is parent_app
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
    assert this_app() is parent_app
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


class Grandparent(Application):
    pass


grand_parent_app = Grandparent()


# parent_app_pc = grand_parent_app.precompile(parent_app)


@grand_parent_app.external
def create_parent(*, output: abi.Uint64) -> Expr:
    """Create a new parent app."""
    assert this_app() is grand_parent_app
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


@grand_parent_app.external
def foo_bar() -> Expr:
    parent_app_pc = precompiled(parent_app)
    assert this_app() is grand_parent_app
    return Seq(Approve())
