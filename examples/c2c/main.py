from pyteal import (
    abi,
    TealType,
    TxnType,
    Seq,
    Assert,
    Len,
    InnerTxnBuilder,
    TxnField,
    Int,
    InnerTxn,
    ScratchVar,
)
from beaker import Application, external, sandbox, client, consts, testing, internal
from beaker.application import get_method_signature


class C2CSub(Application):
    @external
    def opt_in_to_asset(self, asset: abi.Asset):
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: asset.asset_id(),
                TxnField.asset_receiver: self.address,
                TxnField.fee: Int(0),
                TxnField.asset_amount: Int(0),
            }
        )

    @external
    def return_asset(self, asset: abi.Asset, addr: abi.Account):
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


class C2CMain(Application):
    @internal(TealType.uint64)
    def create_asset(self, name):
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: name,
                    TxnField.config_asset_total: Int(10),
                    TxnField.config_asset_manager: self.address,
                }
            ),
            # Get the asset id
            InnerTxn.created_asset_id(),
        )

    @internal(TealType.none)
    def trigger_opt_in_and_xfer(self, app_id, app_addr, asset_id):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.MethodCall(
                app_id=app_id,
                method_signature=get_method_signature(C2CSub.opt_in_to_asset),
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

    @internal(TealType.none)
    def trigger_return(self, app_id, asset_id):
        # Create the group txn to ask sub app to opt in and send sub app 1 token
        # Tell the sub app to send me back the stuff i sent it
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.MethodCall(
                app_id=app_id,
                method_signature=get_method_signature(C2CSub.return_asset),
                args=[asset_id, self.address],
            ),
            InnerTxnBuilder.Submit(),
        )

    @external
    def create_asset_and_send(
        self, name: abi.String, sub_app: abi.Application, *, output: abi.Uint64
    ):
        return Seq(
            Assert(Len(name.get())),
            # Create the asset
            (asset_id := ScratchVar()).store(self.create_asset(name.get())),
            # Get the sub app addr
            (sub_app_addr := sub_app.params().address()),
            # Ask sub app to opt in, and send asset in the same group
            self.trigger_opt_in_and_xfer(
                sub_app.application_id(), sub_app_addr.value(), asset_id.load()
            ),
            # Get the asset back
            self.trigger_return(sub_app.application_id(), asset_id.load()),
            # Return the asset id
            output.set(asset_id.load()),
        )


if __name__ == "__main__":

    accts = sandbox.get_accounts()
    acct = accts.pop()

    # Create sub app
    app_sub = C2CSub()
    app_client_sub = client.ApplicationClient(
        sandbox.get_algod_client(), app_sub, signer=acct.signer
    )
    app_client_sub.create()

    # Create main app and fund it
    app_main = C2CMain()
    app_client_main = client.ApplicationClient(
        sandbox.get_algod_client(), app_main, signer=acct.signer
    )
    app_client_main.create()
    app_client_main.fund(1 * consts.algo)

    # Call main app method to:
    #   create the asset
    #   call the sub app optin method
    #   send asset to sub app
    #   call the sub app return asset method
    sp = app_client_main.client.suggested_params()
    sp.flat_fee = True
    sp.fee = 1 * consts.algo
    result = app_client_main.call(
        app_main.create_asset_and_send,
        name="dope asset",
        sub_app=app_client_sub.app_id,
        suggested_params=sp,
    )
    print(f"Created asset id: {result.return_value}")

    print(
        testing.get_balances(
            app_client_sub.client, [app_client_sub.app_addr, app_client_main.app_addr]
        )
    )
