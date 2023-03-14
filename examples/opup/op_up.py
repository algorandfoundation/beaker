from collections.abc import Callable

import pyteal as pt

import beaker


class OpUpState:
    #: The id of the app created during `bootstrap`
    opup_app_id = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, key="ouaid", static=True
    )


def op_up_blueprint(app: beaker.Application[OpUpState]) -> Callable[[], pt.Expr]:
    target_app = beaker.Application(
        name="TargetApp",
        descr="""Simple app that allows the creator to call `opup` in order to increase its opcode budget""",
    )

    @target_app.external(authorize=beaker.Authorize.only_creator())
    def opup() -> pt.Expr:
        return pt.Approve()

    #: The minimum balance required for this class
    min_balance = beaker.consts.Algos(0.1)

    @app.external
    def opup_bootstrap(
        ptxn: pt.abi.PaymentTransaction, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        """initialize opup with bootstrap to create a target app"""
        return pt.Seq(
            pt.Assert(ptxn.get().amount() >= min_balance),
            create_opup(),
            output.set(app.state.opup_app_id),
        )

    @pt.Subroutine(pt.TealType.none)
    def create_opup() -> pt.Expr:
        """internal method to create the target application"""
        #: The app to be created to receiver opup requests
        target = beaker.precompiled(target_app)

        return pt.Seq(
            pt.InnerTxnBuilder.Begin(),
            pt.InnerTxnBuilder.SetFields(
                {
                    **target.get_create_config(),
                    pt.TxnField.fee: pt.Int(0),
                }
            ),
            pt.InnerTxnBuilder.Submit(),
            app.state.opup_app_id.set(pt.InnerTxn.created_application_id()),
        )

    # No decorator, inline it
    def call_opup() -> pt.Expr:
        """internal method to just return the method call to our target app"""
        return pt.InnerTxnBuilder.ExecuteMethodCall(
            app_id=app.state.opup_app_id,
            method_signature=opup.method_signature(),
            args=[],
            extra_fields={pt.TxnField.fee: pt.Int(0)},
        )

    return call_opup
