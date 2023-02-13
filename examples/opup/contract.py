from typing import Literal

from pyteal import (
    abi,
    ScratchVar,
    Seq,
    Assert,
    Int,
    For,
    Sha256,
    Expr,
)

from beaker import sandbox, Application, unconditional_create_approval
from examples.opup.op_up import op_up_blueprint, OpUpState


expensive_app = Application(
    name="ExpensiveApp",
    descr="""Do expensive work to demonstrate implementing op_up blueprint""",
    state=OpUpState(),
).implement(unconditional_create_approval)

call_opup = op_up_blueprint(expensive_app)


@expensive_app.external
def hash_it(
    input: abi.String,
    iters: abi.Uint64,
    opup_app: abi.Application = expensive_app.state.opup_app_id,  # type: ignore[assignment]
    *,
    output: abi.StaticBytes[Literal[32]],
) -> Expr:
    return Seq(
        Assert(opup_app.application_id() == expensive_app.state.opup_app_id),
        Repeat(255, call_opup()),
        (current := ScratchVar()).store(input.get()),
        For(
            (i := ScratchVar()).store(Int(0)),
            i.load() < iters.get(),
            i.store(i.load() + Int(1)),
        ).Do(current.store(Sha256(current.load()))),
        output.decode(current.load()),
    )


def Repeat(n: int, expr: Expr) -> Expr:
    """internal method to issue transactions against the target app"""
    if n < 0:
        raise ValueError("n < 0")
    elif n == 1:
        return expr
    else:
        return For(
            (i := ScratchVar()).store(Int(0)),
            i.load() < Int(n),
            i.store(i.load() + Int(1)),
        ).Do(expr)


if __name__ == "__main__":
    compiled = expensive_app.build(sandbox.get_algod_client())
    print(compiled.approval_program, compiled.clear_program)
