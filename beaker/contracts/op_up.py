from typing import Final
from pyteal import *

from beaker.application import Application
from beaker.application_schema import GlobalStateValue


class OpUp(Application):
    app_id: Final[GlobalStateValue] = GlobalStateValue(stack_type=TealType.uint64, key=Bytes("ouaid"), static=True)

    @internal(TealType.none)
    def create_opup():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.approval_program: Bytes(""),
                TxnField.clear_state_program: Bytes(""),
            }),
            InnerTxnBuilder.Submit(),
            OpUp.app_id.set(InnerTxn.created_application_id())
        )

    @internal(TealType.none)
    def call():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: OpUp.app_id,
            }),
            InnerTxnBuilder.Submit(),
            OpUp.app_id.set(InnerTxn.created_application_id())
        )

    @internal(TealType.none)
    def call_n(n):
        return For((i:=ScratchVar()).store(Int(0)), i.load()<n, i.store(i.load() + Int(1))).Do(
                OpUp.call()
            )