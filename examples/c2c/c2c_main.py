import pyteal as pt

import beaker

from examples.c2c import c2c_sub

app = beaker.Application(
    "C2CMain",
    descr="Main application that handles creation of the sub app and asset and calls it",
)


@app.external
def create_sub(*, output: pt.abi.Uint64) -> pt.Expr:
    # Create sub app to be precompiled before allowing TEAL generation
    sub_app_pc = beaker.precompiled(c2c_sub.app)

    return pt.Seq(
        pt.InnerTxnBuilder.Execute(sub_app_pc.get_create_config()),
        # return the app id of the newly created app
        output.set(pt.InnerTxn.created_application_id()),
        # Try to read the global state
        sv := c2c_sub.app.state.asv.get_external(output.get()),
        pt.Log(sv.value()),
        # Opt in to the new app for funsies
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.ApplicationCall,
                pt.TxnField.application_id: output.get(),
                pt.TxnField.on_completion: pt.OnComplete.OptIn,
            }
        ),
        # Try to read the local state
        sv := c2c_sub.app.state.acsv[
            pt.Global.current_application_address()
        ].get_external(output.get()),
        pt.Log(sv.value()),
    )


@app.external
def create_asset_and_send(
    name: pt.abi.String, sub_app_ref: pt.abi.Application, *, output: pt.abi.Uint64
) -> pt.Expr:
    return pt.Seq(
        pt.Assert(pt.Len(name.get())),
        # Create the asset
        (asset_id := pt.ScratchVar()).store(create_asset(name.get())),
        # Get the sub app addr
        (sub_app_addr := sub_app_ref.params().address()),
        # Ask sub app to opt in, and send asset in the same group
        trigger_opt_in_and_xfer(
            sub_app_ref.application_id(), sub_app_addr.value(), asset_id.load()
        ),
        # Get the asset back
        trigger_return(sub_app_ref.application_id(), asset_id.load()),
        # Return the asset id
        output.set(asset_id.load()),
    )


@pt.Subroutine(pt.TealType.none)
def trigger_return(app_id: pt.Expr, asset_id: pt.Expr) -> pt.Expr:
    # Create the group txn to ask sub app to opt in and send sub app 1 token
    # Tell the sub app to send me back the stuff i sent it
    return pt.Seq(
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.MethodCall(
            app_id=app_id,
            method_signature=c2c_sub.return_asset.method_signature(),
            args=[asset_id, pt.Global.current_application_address()],
        ),
        pt.InnerTxnBuilder.Submit(),
    )


@pt.Subroutine(pt.TealType.uint64)
def create_asset(name: pt.Expr) -> pt.Expr:
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetConfig,
                pt.TxnField.config_asset_name: name,
                pt.TxnField.config_asset_total: pt.Int(10),
                pt.TxnField.config_asset_manager: pt.Global.current_application_address(),
            }
        ),
        # return the newly created asset id
        pt.InnerTxn.created_asset_id(),
    )


@pt.Subroutine(pt.TealType.none)
def trigger_opt_in_and_xfer(
    app_id: pt.Expr, app_addr: pt.Expr, asset_id: pt.Expr
) -> pt.Expr:
    # Call the sub app to make it opt in and xfer it some tokens
    return pt.Seq(
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.MethodCall(
            app_id=app_id,
            method_signature=c2c_sub.opt_in_to_asset.method_signature(),
            args=[asset_id],
        ),
        pt.InnerTxnBuilder.Next(),
        pt.InnerTxnBuilder.SetFields(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.xfer_asset: asset_id,
                pt.TxnField.asset_amount: pt.Int(1),
                pt.TxnField.asset_receiver: app_addr,
            }
        ),
        pt.InnerTxnBuilder.Submit(),
    )


@app.external
def delete_asset(asset: pt.abi.Asset) -> pt.Expr:
    return pt.InnerTxnBuilder.Execute(
        {
            pt.TxnField.type_enum: pt.TxnType.AssetConfig,
            pt.TxnField.config_asset: asset.asset_id(),
        }
    )
