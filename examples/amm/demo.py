from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.v2client.algod import AlgodClient

from beaker import consts
from beaker.client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client

from examples.amm import amm


def main() -> None:
    # Take first account from sandbox
    acct = get_accounts().pop()
    addr, sk, signer = acct.address, acct.private_key, acct.signer

    # get sandbox client
    client = get_algod_client()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, amm.app, signer=signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    # Fund App address so it can create the pool token and hold balances

    # Create assets
    asset_a = create_asset(client, addr, sk, "A")
    asset_b = create_asset(client, addr, sk, "B")
    print(f"Created asset a/b with ids: {asset_a}/{asset_b}")

    # Call app to create pool token
    print("Calling bootstrap")
    sp = client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(addr, sp, app_addr, int(1e7)), signer=signer
    )
    sp.flat_fee = True
    sp.fee = consts.milli_algo * 4
    result = app_client.call(
        amm.bootstrap,
        seed=ptxn,
        a_asset=asset_a,
        b_asset=asset_b,
        suggested_params=sp,
    )
    pool_token = result.return_value

    def print_balances() -> None:
        addrbal = client.account_info(addr)
        assert isinstance(addrbal, dict)

        print("Participant: ")
        for asset in addrbal["assets"]:
            if asset["asset-id"] == pool_token:
                print("\tPool Balance {}".format(asset["amount"]))
            if asset["asset-id"] == asset_a:
                print("\tAssetA Balance {}".format(asset["amount"]))
            if asset["asset-id"] == asset_b:
                print("\tAssetB Balance {}".format(asset["amount"]))

        appbal = client.account_info(app_addr)
        assert isinstance(appbal, dict)
        print("App: ")
        for asset in appbal["assets"]:
            if asset["asset-id"] == pool_token:
                print("\tPool Balance {}".format(asset["amount"]))
            if asset["asset-id"] == asset_a:
                print("\tAssetA Balance {}".format(asset["amount"]))
            if asset["asset-id"] == asset_b:
                print("\tAssetB Balance {}".format(asset["amount"]))

        state = app_client.get_global_state()
        state_key = amm.app.state.ratio.str_key()
        if state_key in state:
            print(f"\tCurrent ratio a/b == {int(state[state_key]) / amm.SCALE}")
        else:
            print("\tNo ratio a/b")

    print(f"Created pool token with id: {pool_token}")
    print_balances()

    # Opt user into token
    sp = client.suggested_params()
    atc = AtomicTransactionComposer()
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, addr, 0, pool_token),
            signer=signer,
        )
    )
    atc.execute(client, 2)
    print_balances()

    # Cover any fees incurred by inner transactions, maybe overpaying but thats ok
    sp = client.suggested_params()
    sp.flat_fee = True
    sp.fee = consts.milli_algo * 3

    ###
    # Fund Pool with initial liquidity
    ###
    print("Funding")
    app_client.call(
        amm.mint,
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 10000, asset_a),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 3000, asset_b),
            signer=signer,
        ),
        suggested_params=sp,
    )
    print_balances()

    ###
    # Mint pool tokens
    ###
    print("Minting")
    app_client.call(
        amm.mint,
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 100000, asset_a),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 1000, asset_b),
            signer=signer,
        ),
        suggested_params=sp,
    )
    print_balances()

    ###
    # Swap A for B
    ###
    print("Swapping A for B")
    app_client.call(
        amm.swap,
        swap_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 500, asset_a),
            signer=signer,
        ),
    )
    print_balances()

    ###
    # Swap B for A
    ###
    print("Swapping B for A")
    app_client.call(
        amm.swap,
        swap_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 500, asset_b),
            signer=signer,
        ),
    )
    print_balances()

    ###
    # Burn pool tokens
    ###
    print("Burning")
    app_client.call(
        amm.burn,
        pool_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, 100, pool_token),
            signer=signer,
        ),
    )
    print_balances()


def create_asset(client: AlgodClient, addr: str, pk: str, unitname: str) -> int:
    # Get suggested params from network
    sp = client.suggested_params()
    # Create the transaction
    create_txn = transaction.AssetCreateTxn(
        addr,
        sp,
        1000000,
        0,
        default_frozen=False,
        asset_name="asset",
        unit_name=unitname,
    )
    # Ship it
    txid = client.send_transaction(create_txn.sign(pk))
    # Wait for the result so we can return the app id
    result = transaction.wait_for_confirmation(client, txid, 4)
    return result["asset-index"]


if __name__ == "__main__":
    main()
