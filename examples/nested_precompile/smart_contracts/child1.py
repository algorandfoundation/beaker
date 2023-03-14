import pyteal as pt

import beaker


class Child1State:
    counter = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
    )


app = (
    beaker.Application("Child1", state=Child1State())
    # initialise default state values on create
    .apply(beaker.unconditional_create_approval, initialize_global_state=True)
)


@app.external
def increment_counter(*, output: pt.abi.Uint64) -> pt.Expr:
    """Increment the counter global state."""
    return pt.Seq(
        app.state.counter.increment(),
        output.set(app.state.counter.get()),
    )
