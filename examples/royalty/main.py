from algosdk.future import transaction

from beaker.client import ApplicationClient
from beaker.sandbox import get_algod_client, get_accounts

from contract import MyRoyaltyContract


client = get_algod_client()
acct = get_accounts().pop()


def demo():
    # Initialize Application from amm.py
    app = MyRoyaltyContract()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app, signer=acct.signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    sp = client.suggested_params()
    txid = client.send_transaction(
        transaction.PaymentTxn(acct.address, sp, app_addr, int(1e6)).sign(
            acct.private_key
        )
    )
    transaction.wait_for_confirmation(client, txid, 4)

    result = app_client.call(app.create_nft, name="cool-nft")
    print(f"Created nft with id: {result.return_value}")


if __name__ == "__main__":
    demo()
