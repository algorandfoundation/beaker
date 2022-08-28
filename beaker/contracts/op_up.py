from typing import Final
from pyteal import (
    If,
    Txn,
    Return,
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
)

from beaker.application import Application
from beaker.state import ApplicationStateValue
from beaker.consts import Algos
from beaker.decorators import internal, external


OpUpTarget = Return(Txn.sender() == Global.creator_address())
OpUpTargetBinary = "BjEAMgkSQw=="

OpUpClear = Return(Int(1))
OpUpClearBinary = "BoEBQw=="


class OpUp(Application):
    """OpUp creates a "target" application to make opup calls against in order to increase our opcode budget."""

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
                    TxnField.approval_program: Bytes("base64", OpUpTargetBinary),
                    TxnField.clear_state_program: Bytes("base64", OpUpClearBinary),
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
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: OpUp.opup_app_id,
                TxnField.fee: Int(0),
            }
        )
