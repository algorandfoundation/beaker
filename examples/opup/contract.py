from typing import Literal

import pyteal as pt

import beaker

from examples.opup.op_up import OpUpState, op_up_blueprint

app = beaker.Application(
    name="ExpensiveApp",
    descr="Do expensive work to demonstrate implementing op_up blueprint",
    state=OpUpState(),
)

# Create a callable method after passing the
# instance of the app to have methods added
call_opup = op_up_blueprint(app)


@app.external
def hash_it(
    input: pt.abi.String,
    iters: pt.abi.Uint64,
    opup_app: pt.abi.Application = app.state.opup_app_id,  # type: ignore[assignment]
    *,
    output: pt.abi.StaticBytes[Literal[32]],
) -> pt.Expr:
    return pt.Seq(
        pt.Assert(opup_app.application_id() == app.state.opup_app_id),
        Repeat(255, call_opup()),
        (current := pt.ScratchVar()).store(input.get()),
        pt.For(
            (i := pt.ScratchVar()).store(pt.Int(0)),
            i.load() < iters.get(),
            i.store(i.load() + pt.Int(1)),
        ).Do(current.store(pt.Sha256(current.load()))),
        output.decode(current.load()),
    )


def Repeat(n: int, expr: pt.Expr) -> pt.Expr:  # noqa: N802
    """internal method to issue transactions against the target app"""
    if n < 0:
        raise ValueError("n < 0")
    elif n == 1:
        return expr
    else:
        return pt.For(
            (i := pt.ScratchVar()).store(pt.Int(0)),
            i.load() < pt.Int(n),
            i.store(i.load() + pt.Int(1)),
        ).Do(expr)
