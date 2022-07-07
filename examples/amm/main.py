import base64

from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.atomic_transaction_composer import *

from amm import ConstantProductAMM
from beaker import ApplicationClient
from beaker.sandbox import get_accounts, get_client


client = get_client()

addr, sk = get_accounts().pop()
signer = AccountTransactionSigner(sk)

def demo():

    # Initialize Application from amm.py
    app = ConstantProductAMM()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create(signer)
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    # Fund App address so it can create the pool token and hold balances
    sp = client.suggested_params()
    txid = client.send_transaction(
        transaction.PaymentTxn(addr, sp, app_addr, int(1e7)).sign(sk)
    )
    transaction.wait_for_confirmation(client, txid, 4)

    # Create assets
    asset_a = create_asset(addr, sk, "A")
    asset_b = create_asset(addr, sk, "B")
    print(f"Created asset a/b with ids: {asset_a}/{asset_b}")

    # Call app to create pool token
    result = app_client.call(signer, app.bootstrap.method_spec(), [asset_a, asset_b])
    pool_token = result.abi_results[0].return_value
    print(f"Created pool token with id: {pool_token}")
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

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
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

    ###
    # Fund Pool with initial liquidity
    ###
    print("Funding")
    app_client.call(
        signer,
        app.mint.method_spec(),
        [
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 10000, asset_a),
                signer=signer,
            ),
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 3000, asset_b),
                signer=signer,
            ),
            pool_token,
            asset_a,
            asset_b,
        ],
    )
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

    ###
    # Mint pool tokens
    ###
    print("Minting")
    app_client.call(
        signer,
        app.mint.method_spec(),
        [
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 100000, asset_a),
                signer=signer,
            ),
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 1000, asset_b),
                signer=signer,
            ),
            pool_token,
            asset_a,
            asset_b,
        ],
    )
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

    ###
    # Swap A for B
    ###
    print("Swapping A for B")
    app_client.call(
        signer,
        app.swap.method_spec(),
        [
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 500, asset_a),
                signer=signer,
            ),
            asset_a,
            asset_b,
        ],
    )
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

    ###
    # Swap B for A
    ###
    print("Swapping B for A")
    app_client.call(
        signer,
        app.swap.method_spec(),
        [
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 500, asset_b),
                signer=signer,
            ),
            asset_a,
            asset_b,
        ],
    )
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)

    ###
    # Burn pool tokens
    ###
    print("Burning")
    app_client.call(
        signer,
        app.burn.method_spec(),
        [
            TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 100, pool_token),
                signer=signer,
            ),
            pool_token,
            asset_a,
            asset_b,
        ],
    )
    print_balances(app_id, app_addr, addr, pool_token, asset_a, asset_b)


def create_asset(addr, pk, unitname):
    # Get suggested params from network
    sp = client.suggested_params()
    # Create the transaction
    create_txn = transaction.AssetCreateTxn(
        addr, sp, 1000000, 0, False, asset_name="asset", unit_name=unitname
    )
    # Ship it
    txid = client.send_transaction(create_txn.sign(pk))
    # Wait for the result so we can return the app id
    result = transaction.wait_for_confirmation(client, txid, 4)
    return result["asset-index"]


def print_balances(app_id: int, app: str, addr: str, pool: int, a: int, b: int):

    addrbal = client.account_info(addr)
    print("Participant: ")
    for asset in addrbal["assets"]:
        if asset["asset-id"] == pool:
            print("\tPool Balance {}".format(asset["amount"]))
        if asset["asset-id"] == a:
            print("\tAssetA Balance {}".format(asset["amount"]))
        if asset["asset-id"] == b:
            print("\tAssetB Balance {}".format(asset["amount"]))

    appbal = client.account_info(app)
    print("App: ")
    for asset in appbal["assets"]:
        if asset["asset-id"] == pool:
            print("\tPool Balance {}".format(asset["amount"]))
        if asset["asset-id"] == a:
            print("\tAssetA Balance {}".format(asset["amount"]))
        if asset["asset-id"] == b:
            print("\tAssetB Balance {}".format(asset["amount"]))

    app_state = client.application_info(app_id)
    state = {}
    for sv in app_state["params"]["global-state"]:
        key = base64.b64decode(sv["key"]).decode("utf-8")
        match sv["value"]["type"]:
            case 1:
                val = f"0x{base64.b64decode(sv['value']['bytes']).hex()}"
            case 2:
                val = sv["value"]["uint"]
            case 3:
                pass
        state[key] = val

    if "r" in state:
        print(
            f"\tCurrent ratio a/b == {state['r'] / 1000}"
        )  # TODO: dont hardcode the scale
    else:
        print("\tNo ratio a/b")


if __name__ == "__main__":
    demo()
