from algosdk.atomic_transaction_composer import AccountTransactionSigner

from beaker.client import ApplicationClient
from beaker.sandbox import get_client, get_accounts

from contract import MySickApp


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)


def demo():
    # Initialize Application from amm.py
    app = MySickApp()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app, signer=signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    app_client = app_client.prepare(signer=signer, sp=client.suggested_params())

    result = app_client.call(app.add, a=2, b=3)
    print(result.return_value)

    result = app_client.call(app.increment)
    print(result.return_value)

    result = app_client.call(app.decrement)
    print(result.return_value)


if __name__ == "__main__":
    demo()
