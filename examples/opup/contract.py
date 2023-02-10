from typing import Literal

from pyteal import (
    abi,
    ScratchVar,
    Seq,
    Assert,
    Int,
    For,
    Sha256,
)

from beaker import sandbox, Application, unconditional_create_approval
from examples.opup.op_up import op_up_blueprint, OpUpState, Repeat


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
    opup_app: abi.Application = OpUpState.opup_app_id,  # type: ignore[assignment]
    *,
    output: abi.StaticBytes[Literal[32]],
):
    return Seq(
        Assert(opup_app.application_id() == OpUpState.opup_app_id),
        Repeat(255, call_opup()),
        (current := ScratchVar()).store(input.get()),
        For(
            (i := ScratchVar()).store(Int(0)),
            i.load() < iters.get(),
            i.store(i.load() + Int(1)),
        ).Do(current.store(Sha256(current.load()))),
        output.decode(current.load()),
    )


if __name__ == "__main__":
    compiled = expensive_app.build(sandbox.get_algod_client())
    print(compiled.approval_program, compiled.clear_program)
