from pyteal import *


def axfer(asset_id: Expr, amount: Expr, receiver: Expr) -> dict[TxnField, Expr]:
    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.xfer_asset: asset_id,
        TxnField.asset_amount: amount,
        TxnField.asset_receiver: receiver,
    }


def clawback_axfer(
    asset_id: Expr, amount: Expr, receiver: Expr, clawback_addr: Expr
) -> dict[TxnField, Expr]:
    return axfer(asset_id, amount, receiver) | {
        TxnField.asset_sender: clawback_addr,
    }
