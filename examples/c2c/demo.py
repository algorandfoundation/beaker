import beaker

from examples.c2c import c2c_main


def main() -> None:
    accts = beaker.sandbox.get_accounts()
    acct = accts.pop()
    algod_client = beaker.sandbox.get_algod_client()

    # Create main app and fund it
    app_client = beaker.client.ApplicationClient(
        algod_client, c2c_main.app, signer=acct.signer
    )
    main_app_id, _, _ = app_client.create()

    print(f"Created main app: {main_app_id}")
    app_client.fund(1 * beaker.consts.algo)

    # Call the main app to create the sub app
    result = app_client.call(c2c_main.create_sub)
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
    sp.fee = 1 * beaker.consts.algo
    result = app_client.call(
        c2c_main.create_asset_and_send,
        name="dope asset",
        sub_app_ref=sub_app_id,
        suggested_params=sp,
    )
    created_asset = result.return_value
    print(f"Created asset id: {created_asset}")

    result = app_client.call(c2c_main.delete_asset, asset=created_asset)
    print(f"Deleted asset in tx: {result.tx_id}")


if __name__ == "__main__":
    main()
