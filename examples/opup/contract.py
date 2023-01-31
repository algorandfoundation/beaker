from typing import Literal
from pyteal import (
    abi,
    ScratchVar,
    Seq,
    Assert,
    Int,
    For,
    Sha256,
    InnerTxnBuilder,
    TxnField,
    Expr,
)
from beaker import sandbox, Application

if __name__ == "__main__":
    from op_up import OpUp, OpUpState, Repeat, TargetApp  # type: ignore
else:
    from .op_up import OpUp, OpUpState, Repeat, TargetApp


def ExpensiveApp() -> Application:

    target_app = TargetApp()

    app = OpUp(
        target_app=target_app,
        name="ExpensiveApp",
        descr="""Do expensive work to demonstrate inheriting from OpUp""",
    )

    @app.external
    def hash_it(
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application = OpUpState.opup_app_id,
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

    # No decorator, inline it
    def call_opup() -> Expr:
        """internal method to just return the method call to our target app"""
        return InnerTxnBuilder.ExecuteMethodCall(
            app_id=OpUpState.opup_app_id,
            method_signature=target_app.abi_methods["opup"].method_signature(),
            args=[],
            extra_fields={TxnField.fee: Int(0)},
        )

    return app


if __name__ == "__main__":
    a, c = ExpensiveApp().compile(sandbox.get_algod_client())
    print(a, c)
