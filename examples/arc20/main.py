from algosdk.atomic_transaction_composer import AccountTransactionSigner
from beaker.contracts.arcs import ARC20
from beaker.sandbox import get_accounts, get_client
from beaker.client import ApplicationClient

accts = get_accounts()
algod_client = get_client()


def demo():

    addr, sk = accts.pop()
    signer = AccountTransactionSigner(sk)

    app = ARC20()

    app_client = ApplicationClient(algod_client, app=app, signer=signer)

    app_id, app_addr, txid = app_client.create()
    print(f"Created app: {app_id} with address {app_addr}")


if __name__ == "__main__":
    demo()
