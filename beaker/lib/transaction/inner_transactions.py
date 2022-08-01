from pyteal import Expr, InnerTxnBuilder, Seq, Subroutine, TealType, TxnField, TxnType


@Subroutine(TealType.none)
def axfer(receiver, asset_id, amt) -> Expr:
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.asset_receiver: receiver,
                TxnField.xfer_asset: asset_id,
                TxnField.asset_amount: amt,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def pay(receiver, amt) -> Expr:
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: receiver,
                TxnField.amount: amt,
            }
        ),
        InnerTxnBuilder.Submit(),
    )
