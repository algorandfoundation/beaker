from algosdk.atomic_transaction_composer import AccountTransactionSigner

from beaker import ApplicationClient, method_spec
from beaker.sandbox import get_client, get_accounts

from contract import MySickApp


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)


def demo():
    # Initialize Application from amm.py
    app = MySickApp()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create(signer)
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    result = app_client.call(signer, method_spec(app.add), [2, 3])
    print(result.abi_results[0].return_value)

    result = app_client.call(signer, method_spec(app.increment))
    print(result.abi_results[0].return_value)

    result = app_client.call(signer, method_spec(app.decrement))
    print(result.abi_results[0].return_value)


if __name__ == "__main__":
    demo()
