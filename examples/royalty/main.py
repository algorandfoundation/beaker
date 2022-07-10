from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk.future import transaction

from beaker.client import ApplicationClient
from beaker.sandbox import get_client, get_accounts

from contract import MyRoyaltyContract


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)


def demo():
    # Initialize Application from amm.py
    app = MyRoyaltyContract()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create(signer)
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    sp = client.suggested_params()
    txid = client.send_transaction(
        transaction.PaymentTxn(addr, sp, app_addr, int(1e6)).sign(sk)
    )
    transaction.wait_for_confirmation(client, txid, 4)

    result = app_client.call(signer, app.create_nft, ["cool-nft"])
    print(f"Created nft with id: {result.abi_results[0].return_value}")


if __name__ == "__main__":
    demo()
