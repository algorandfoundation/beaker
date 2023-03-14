import pyteal as pt

import beaker


class C2CSubState:
    rasv = beaker.ReservedGlobalStateValue(pt.TealType.bytes, 1)
    asv = beaker.GlobalStateValue(pt.TealType.bytes, default=pt.Bytes("asv"))

    racsv = beaker.ReservedLocalStateValue(pt.TealType.bytes, 1)
    acsv = beaker.LocalStateValue(pt.TealType.bytes, default=pt.Bytes("acsv"))


app = (
    beaker.Application(
        "C2CSub",
        descr="Sub application whose only purpose is to opt into then close out of an asset",
        state=C2CSubState(),
    )
    .apply(beaker.unconditional_create_approval, initialize_global_state=True)
    .apply(beaker.unconditional_opt_in_approval, initialize_local_state=True)
)


@app.external
def opt_in_to_asset(asset: pt.abi.Asset) -> pt.Expr:
    return pt.InnerTxnBuilder.Execute(
        {
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: asset.asset_id(),
            pt.TxnField.asset_receiver: pt.Global.current_application_address(),
            pt.TxnField.fee: pt.Int(0),
            pt.TxnField.asset_amount: pt.Int(0),
        }
    )


@app.external
def return_asset(asset: pt.abi.Asset, addr: pt.abi.Account) -> pt.Expr:
    return pt.InnerTxnBuilder.Execute(
        {
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: asset.asset_id(),
            pt.TxnField.asset_receiver: addr.address(),
            pt.TxnField.fee: pt.Int(0),
            pt.TxnField.asset_amount: pt.Int(0),
            pt.TxnField.asset_close_to: addr.address(),
        }
    )
