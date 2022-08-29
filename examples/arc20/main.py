from algosdk.future.transaction import (
    AssetOptInTxn,
    OnComplete,
)
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
)
from beaker.contracts.arcs import ARC20
from beaker.sandbox import get_accounts, get_algod_client
from beaker.client import ApplicationClient

accts = get_accounts()
algod_client = get_algod_client()


def demo():

    acct = accts.pop()

    app_client = ApplicationClient(algod_client, app=ARC20(), signer=acct.signer)

    app_id, app_addr, txid = app_client.create()
    print(f"Created app: {app_id} with address {app_addr}")

    app_client.fund(int(1e6))

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = sp.min_fee * 2

    result = app_client.call(
        ARC20.asset_create,
        suggested_params=sp,
        total=100,
        decimals=0,
        default_frozen=False,
        unit_name="tst",
        name="Tester",
        url="https://test.com",
        metadata_hash="",
        manager_addr=acct.address,
        freeze_addr=acct.address,
        clawback_addr=acct.address,
        reserve_addr=acct.address,
    )

    smart_asa_id = result.return_value

    print(f"Created asset with asset id: {smart_asa_id}")

    result = app_client.call(
        ARC20.asset_config,
        suggested_params=sp,
        config_asset=smart_asa_id,
        total=200,
        decimals=0,
        default_frozen=False,
        unit_name="tst",
        name="Tester",
        url="https://test.com",
        metadata_hash="",
        manager_addr=acct.address,
        freeze_addr=acct.address,
        clawback_addr=acct.address,
        reserve_addr=acct.address,
    )

    print(f"Reconfigured asset id: {smart_asa_id}")

    try:
        result = app_client.call(
            ARC20.asset_app_optin,
            suggested_params=sp,
            on_complete=OnComplete.OptInOC,
            asset=smart_asa_id,
            opt_in_txn=TransactionWithSigner(
                txn=AssetOptInTxn(acct.address, sp, smart_asa_id),
                signer=acct.signer,
            ),
        )
    except Exception as e:
        print(app_client.wrap_approval_exception(e, 100))

    acct2 = accts.pop()

    client2 = app_client.prepare(signer=acct2.signer)
    result = client2.call(
        ARC20.asset_app_optin,
        suggested_params=sp,
        on_complete=OnComplete.OptInOC,
        asset=smart_asa_id,
        opt_in_txn=TransactionWithSigner(
            txn=AssetOptInTxn(acct2.address, sp, smart_asa_id),
            signer=acct2.signer,
        ),
    )

    app_client.call(
        ARC20.asset_transfer,
        suggested_params=sp,
        xfer_asset=smart_asa_id,
        asset_amount=1,
        asset_sender=app_addr,
        asset_receiver=acct2.address,
    )


if __name__ == "__main__":
    demo()
