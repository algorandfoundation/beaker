from pyteal import (
    Approve,
    Expr,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Seq,
    TealType,
    abi,
)

from beaker import (
    Application,
    GlobalStateValue,
    LogicSignature,
    precompiled,
    unconditional_create_approval,
)


class Child1State:
    counter = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )


child1_app = Application("Child1", state=Child1State()).apply(
    unconditional_create_approval, initialize_global_state=True
)


@child1_app.external
def increment_counter(*, output: abi.Uint64) -> Expr:
    """Increment the counter global state."""
    return Seq(
        child1_app.state.counter.increment(),
        output.set(child1_app.state.counter.get()),
    )


child2_app = Application("Child2").apply(unconditional_create_approval)
lsig = LogicSignature(Approve())


@child2_app.external(read_only=True)
def get_lsig_addr(*, output: abi.Address) -> Expr:
    return output.set(precompiled(lsig).address())


parent_app = Application("Parent").apply(unconditional_create_approval)


@parent_app.external
def create_child_1(*, output: abi.Uint64) -> Expr:
    """Create a new child app."""
    c1_app_precompiled = precompiled(child1_app)
    return Seq(
        InnerTxnBuilder.Execute(c1_app_precompiled.get_create_config()),
        output.set(InnerTxn.created_application_id()),
    )


@parent_app.external
def create_child_2(*, output: abi.Uint64) -> Expr:
    """Create a new child app."""
    c2_app_precompiled = precompiled(child2_app)
    return Seq(
        InnerTxnBuilder.Execute(c2_app_precompiled.get_create_config()),
        output.set(InnerTxn.created_application_id()),
    )


grand_parent_app = Application("Grandparent").apply(unconditional_create_approval)


@grand_parent_app.external
def create_parent(*, output: abi.Uint64) -> Expr:
    """Create a new parent app."""
    return Seq(
        InnerTxnBuilder.Execute(precompiled(parent_app).get_create_config()),
        output.set(InnerTxn.created_application_id()),
    )
