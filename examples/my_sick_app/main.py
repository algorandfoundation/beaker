import base64

from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.atomic_transaction_composer import *

from contract import MySickApp
from beaker import ApplicationClient

from sandbox import get_accounts


client = AlgodClient("a" * 64, "http://localhost:4001")


def demo():
    addr, sk = get_accounts()[0]
    signer = AccountTransactionSigner(sk)

    # Initialize Application from amm.py
    app = MySickApp()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create(signer)
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")


    result = app_client.call(signer, app.add.method_spec(), [2,3])    
    print(result.abi_results[0].return_value)


    result = app_client.call(signer, app.increment.method_spec())    
    print(result.abi_results[0].return_value)

    result = app_client.call(signer, app.decrement.method_spec())    
    print(result.abi_results[0].return_value)


if __name__ == "__main__":
    demo()
