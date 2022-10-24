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
)

from beaker.application import Application, get_method_signature
from beaker.precompile import AppPrecompile
from beaker.state import ApplicationStateValue
from beaker.consts import Algos
from beaker.decorators import internal, external, Authorize


class TargetApp(Application):
    """Simple app that allows the creator to call `opup` in order to increase its opcode budget"""

    @external(authorize=Authorize.only(Global.creator_address()))
    def opup(self):
        return Approve()


class OpUp(Application):
    """OpUp creates a "target" application to make opup calls against in order to increase our opcode budget."""

    #: The app to be created to receiver opup requests
    target: AppPrecompile = AppPrecompile(TargetApp())

    #: The minimum balance required for this class
    min_balance: Final[Expr] = Algos(0.1)

    #: The id of the app created during `bootstrap`
    opup_app_id: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, key=Bytes("ouaid"), static=True
    )

    @external
    def opup_bootstrap(self, ptxn: abi.PaymentTransaction, *, output: abi.Uint64):
        """initialize opup with bootstrap to create a target app"""
        return Seq(
            Assert(ptxn.get().amount() >= self.min_balance),
            self.create_opup(),
            output.set(OpUp.opup_app_id),
        )

    @internal(TealType.none)
    def create_opup(self):
        """internal method to create the target application"""
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.target.approval.binary,
                    TxnField.clear_state_program: self.target.clear.binary,
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            self.opup_app_id.set(InnerTxn.created_application_id()),
        )

    @internal(TealType.none)
    def call_opup(self, n):
        """internal method to issue transactions against the target app"""
        return If(
            n == Int(1),
            self.__call_opup(),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < n,
                i.store(i.load() + Int(1)),
            ).Do(Seq(self.__call_opup())),
        )

    # No decorator, inline it
    def __call_opup(self):
        """internal method to just return the method call to our target app"""
        return InnerTxnBuilder.ExecuteMethodCall(
            app_id=self.opup_app_id,
            method_signature=get_method_signature(TargetApp.opup),
            args=[],
            extra_fields={TxnField.fee: Int(0)},
        )
