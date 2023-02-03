from typing import Final
from pyteal import (
    If,
    Global,
    TealType,
    abi,
    InnerTxnBuilder,
    Seq,
    Bytes,
    TxnType,
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

from beaker.application import Application, precompiled
from beaker.blueprints import unconditional_create_approval
from beaker.state import ApplicationStateValue
from beaker.consts import Algos
from beaker.decorators import Authorize


def TargetApp() -> Application:

    app = Application(
        name="TargetApp",
        descr="""Simple app that allows the creator to call `opup` in order to increase its opcode budget""",
    ).implement(unconditional_create_approval)

    @app.external(authorize=Authorize.only(Global.creator_address()))
    def opup():
        return Approve()

    return app


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
        stack_type=TealType.uint64, key=Bytes("ouaid"), static=True
    )


def OpUp(
    target_app: Application, name: str | None = None, descr: str | None = None
) -> Application:
    app = Application(
        name=name or "OpUp",
        state_class=OpUpState,
        descr=descr
        or """OpUp creates a "target" application to make opup calls against in order to increase our opcode budget.""",
    ).implement(unconditional_create_approval)

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
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: target.approval.binary,
                    TxnField.clear_state_program: target.clear.binary,
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            OpUpState.opup_app_id.set(InnerTxn.created_application_id()),
        )

    return app
