from pyteal import (
    abi,
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
from beaker import Application, external, sandbox, client, consts, testing
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
    @external
    def create_asset_and_send(
        self, name: abi.String, sub_app: abi.Application, *, output: abi.Uint64
    ):
        return Seq(
            Assert(Len(name.get())),
            # Create the asset
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: name.get(),
                    TxnField.config_asset_total: Int(10),
                    TxnField.config_asset_manager: self.address,
                }
            ),
            # Get the asset id
            (asset_id := ScratchVar()).store(InnerTxn.created_asset_id()),
            (sub_app_addr := sub_app.params().address()),
            Assert(sub_app_addr.hasValue()),
            # Create the group txn to ask sub app to opt in and send sub app 1 token
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.MethodCall(
                app_id=sub_app.application_id(),
                method_signature=get_method_signature(C2CSub.opt_in_to_asset),
                args=[asset_id.load()],
            ),
            InnerTxnBuilder.Next(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset_id.load(),
                    TxnField.asset_amount: Int(1),
                    TxnField.asset_receiver: sub_app_addr.value(),
                }
            ),
            InnerTxnBuilder.Submit(),
            # Tell the sub app to send me back the stuff i sent it
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.MethodCall(
                app_id=sub_app.application_id(),
                method_signature=get_method_signature(C2CSub.return_asset),
                args=[asset_id.load(), self.address],
            ),
            InnerTxnBuilder.Submit(),
            output.set(asset_id.load()),
        )


if __name__ == "__main__":

    accts = sandbox.get_accounts()
    acct = accts.pop()

    # Create sub app and fund it
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

    # Call main app method to create and send asset to sub app
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

    # Print the transaction result
    # print(app_client_main.client.pending_transaction_info(result.tx_id))

    print(
        testing.get_balances(
            app_client_sub.client, [app_client_sub.app_addr, app_client_main.app_addr]
        )
    )
