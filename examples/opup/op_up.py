from typing import Final, Callable

from pyteal import (
    Global,
    TealType,
    abi,
    InnerTxnBuilder,
    Seq,
    InnerTxn,
    TxnField,
    Assert,
    Expr,
    Int,
    ScratchVar,
    For,
    Approve,
    Subroutine,
)

from beaker import (
    Application,
    precompiled,
    unconditional_create_approval,
    Authorize,
    ApplicationStateValue,
)
from beaker.consts import Algos


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


class OpUpState:
    #: The id of the app created during `bootstrap`
    opup_app_id = ApplicationStateValue(
        stack_type=TealType.uint64, key="ouaid", static=True
    )


def op_up_blueprint(app: Application[OpUpState]) -> Callable[[], Expr]:
    target_app = Application(
        name="TargetApp",
        descr="""Simple app that allows the creator to call `opup` in order to increase its opcode budget""",
    ).implement(unconditional_create_approval)

    @target_app.external(authorize=Authorize.only(Global.creator_address()))
    def opup():
        return Approve()

    #: The minimum balance required for this class
    min_balance: Final[Expr] = Algos(0.1)

    @app.external
    def opup_bootstrap(ptxn: abi.PaymentTransaction, *, output: abi.Uint64):
        """initialize opup with bootstrap to create a target app"""
        return Seq(
            Assert(ptxn.get().amount() >= min_balance),
            create_opup(),
            output.set(OpUpState.opup_app_id),
        )

    @Subroutine(TealType.none)
    def create_opup():
        """internal method to create the target application"""
        #: The app to be created to receiver opup requests
        target = precompiled(target_app)

        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    **target.get_create_config(),
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            OpUpState.opup_app_id.set(InnerTxn.created_application_id()),
        )

    # No decorator, inline it
    def call_opup() -> Expr:
        """internal method to just return the method call to our target app"""
        return InnerTxnBuilder.ExecuteMethodCall(
            app_id=OpUpState.opup_app_id,
            method_signature=opup.method_signature(),  # type: ignore[union-attr]
            args=[],
            extra_fields={TxnField.fee: Int(0)},
        )

    return call_opup
