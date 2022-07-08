from typing import Final
from pyteal import *

from beaker.application import Application
from beaker.application_schema import GlobalStateValue
from beaker.consts import Algo
from beaker.decorators import internal, handler


OpUpTarget = Return(Txn.sender() == Global.creator_address())
OpUpTargetBinary = "BjEAMgkSQw=="

OpUpClear = Return(Int(1))
OpUpClearBinary = "BoEBQw=="


class OpUp(Application):
    min_balance: Final[Int] = Algo
    opup_app_id: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64, key=Bytes("ouaid"), static=True
    )

    @internal(TealType.none)
    def create_opup():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: Bytes("base64", OpUpTargetBinary),
                    TxnField.clear_state_program: Bytes("base64", OpUpClearBinary),
                }
            ),
            InnerTxnBuilder.Submit(),
            OpUp.opup_app_id.set(InnerTxn.created_application_id()),
        )

    @internal(TealType.none)
    def call_opup():
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: OpUp.opup_app_id,
                }
            ),
            InnerTxnBuilder.Submit()
        )

    @internal(TealType.none)
    def call_opup_n(n):
        return For(
            (i := ScratchVar()).store(Int(0)), i.load() < n, i.store(i.load() + Int(1))
        ).Do(OpUp.call_opup())
