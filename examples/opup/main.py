from hashlib import sha256
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    TransactionWithSigner,
)
from algosdk.future import transaction

from beaker import ApplicationClient, method_spec
from beaker.sandbox import get_client, get_accounts

from contract import ExpensiveApp


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)


def demo():
    # Initialize Application from amm.py
    app = ExpensiveApp()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create(signer)
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    sp = client.suggested_params()
    txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(addr, sp, app_addr, int(1e6)), signer=signer
    )
    result = app_client.call(signer, method_spec(app.bootstrap), args=[txn])
    oua = result.abi_results[0].return_value
    print(f"Created op up app: {oua}")

    input = "stuff"
    iters = 10
    result = app_client.call(signer, method_spec(app.hash_it), [input, iters, oua])
    hashed = result.abi_results[0].raw_value[2:]
    print(f"Remote result of hash: {hashed.hex()}")

    hash = input.encode()
    for _ in range(iters):
        hash = sha256(hash).digest()
    print(f"Local result of hash: {hash.hex()}")


if __name__ == "__main__":
    demo()
