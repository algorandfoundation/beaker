from pyteal import (
    Assert,
    Bytes,
    Expr,
    Global,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Len,
    Log,
    OnComplete,
    ScratchVar,
    Seq,
    Subroutine,
    TealType,
    TxnField,
    TxnType,
    abi,
)

import beaker as bkr
from beaker import precompiled

algod_client = bkr.sandbox.get_algod_client()


class C2CSubState:
    rasv = bkr.ReservedGlobalStateValue(TealType.bytes, 1)
    asv = bkr.GlobalStateValue(TealType.bytes, default=Bytes("asv"))

    racsv = bkr.ReservedLocalStateValue(TealType.bytes, 1)
    acsv = bkr.LocalStateValue(TealType.bytes, default=Bytes("acsv"))


sub_app = (
    bkr.Application(
        "C2CSub",
        descr="Sub application who's only purpose is to opt into then close out of an asset",
        state=C2CSubState(),
    )
    .apply(bkr.unconditional_create_approval, initialize_global_state=True)
    .apply(bkr.unconditional_opt_in_approval, initialize_local_state=True)
)


@sub_app.external
def opt_in_to_asset(asset: abi.Asset) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: asset.asset_id(),
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.fee: Int(0),
            TxnField.asset_amount: Int(0),
        }
    )


@sub_app.external
def return_asset(asset: abi.Asset, addr: abi.Account) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: asset.asset_id(),
            TxnField.asset_receiver: addr.address(),
            TxnField.fee: Int(0),
            TxnField.asset_amount: Int(0),
            TxnField.asset_close_to: addr.address(),
        }
    )


main_app = bkr.Application(
    "C2CMain",
    descr="Main application that handles creation of the sub app and asset and calls it",
).apply(bkr.unconditional_create_approval)


@main_app.external
def create_sub(*, output: abi.Uint64) -> Expr:
    # Create sub app to be precompiled before allowing TEAL generation
    sub_app_pc = precompiled(sub_app)

    return Seq(
        InnerTxnBuilder.Execute(sub_app_pc.get_create_config()),
        # return the app id of the newly created app
        output.set(InnerTxn.created_application_id()),
        # Try to read the global state
        sv := sub_app.state.asv.get_external(output.get()),
        Log(sv.value()),
        # Opt in to the new app for funsies
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: output.get(),
                TxnField.on_completion: OnComplete.OptIn,
            }
        ),
        # Try to read the local state
        sv := sub_app.state.acsv[Global.current_application_address()].get_external(
            output.get()
        ),
        Log(sv.value()),
    )


@Subroutine(TealType.uint64)
def create_asset(name: Expr) -> Expr:
    return Seq(
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset_name: name,
                TxnField.config_asset_total: Int(10),
                TxnField.config_asset_manager: Global.current_application_address(),
            }
        ),
        # return the newly created asset id
        InnerTxn.created_asset_id(),
    )


@Subroutine(TealType.none)
def trigger_opt_in_and_xfer(app_id: Expr, app_addr: Expr, asset_id: Expr) -> Expr:
    # Call the sub app to make it opt in and xfer it some tokens
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.MethodCall(
            app_id=app_id,
            method_signature=opt_in_to_asset.method_signature(),
            args=[asset_id],
        ),
        InnerTxnBuilder.Next(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: asset_id,
                TxnField.asset_amount: Int(1),
                TxnField.asset_receiver: app_addr,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def trigger_return(app_id: Expr, asset_id: Expr) -> Expr:
    # Create the group txn to ask sub app to opt in and send sub app 1 token
    # Tell the sub app to send me back the stuff i sent it
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.MethodCall(
            app_id=app_id,
            method_signature=return_asset.method_signature(),
            args=[asset_id, Global.current_application_address()],
        ),
        InnerTxnBuilder.Submit(),
    )


@main_app.external
def create_asset_and_send(
    name: abi.String, sub_app_ref: abi.Application, *, output: abi.Uint64
) -> Expr:
    return Seq(
        Assert(Len(name.get())),
        # Create the asset
        (asset_id := ScratchVar()).store(create_asset(name.get())),
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


@main_app.external
def delete_asset(asset: abi.Asset) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.AssetConfig,
            TxnField.config_asset: asset.asset_id(),
        }
    )


def demo() -> None:

    accts = bkr.sandbox.get_accounts()
    acct = accts.pop()
    algod_client = bkr.sandbox.get_algod_client()

    # Create main app and fund it
    app_client = bkr.client.ApplicationClient(
        algod_client, main_app, signer=acct.signer
    )
    main_app_id, _, _ = app_client.create()

    print(f"Created main app: {main_app_id}")
    app_client.fund(1 * bkr.consts.algo)

    # Call the main app to create the sub app
    result = app_client.call(create_sub)
    print(result.tx_info)
    sub_app_id = result.return_value
    print(f"Created sub app: {sub_app_id}")

    # Call main app method to:
    #   create the asset
    #   call the sub app optin method
    #   send asset to sub app
    #   call the sub app return asset method
    sp = app_client.client.suggested_params()
    sp.flat_fee = True
    sp.fee = 1 * bkr.consts.algo
    result = app_client.call(
        create_asset_and_send,
        name="dope asset",
        sub_app_ref=sub_app_id,
        suggested_params=sp,
    )
    created_asset = result.return_value
    print(f"Created asset id: {created_asset}")

    result = app_client.call(delete_asset, asset=created_asset)
    print(f"Deleted asset in tx: {result.tx_id}")


if __name__ == "__main__":
    demo()
