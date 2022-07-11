from hashlib import sha256
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    TransactionWithSigner,
)
from algosdk.future import transaction

from beaker.client import ApplicationClient
from beaker.sandbox import get_client, get_accounts

from contract import ExpensiveApp


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)


def demo():
    # Initialize Application from amm.py
    app = ExpensiveApp()

    # Create an Application client containing both an algod client and my app
    sp = client.suggested_params()
    app_client = ApplicationClient(client, app, signer=signer, suggested_params=sp)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    txn = TransactionWithSigner(
        txn=transaction.PaymentTxn(addr, sp, app_addr, int(1e6)), signer=signer
    )
    oua = app_client.call(app.opup_bootstrap, ptxn=txn)
    print(f"Created op up app: {oua}")

    input = "stuff"
    iters = 10

    # You can compose calls if you pre-defined your ATC
    # atc = AtomicTransactionComposer()
    # app_client.compose(atc, app.hash_it, input=input, iters=iters)
    # result = atc.execute(client, 4)

    result = app_client.call(app.hash_it, input=input, iters=iters)

    result_hash = bytes(result)

    local_hash = input.encode()
    for _ in range(iters):
        local_hash = sha256(local_hash).digest()

    assert result_hash == local_hash, f"Expected {local_hash} got {result_hash}"

    print(f"Successfully hashed {input},  {iters} times to produce {result_hash.hex()}")


if __name__ == "__main__":
    demo()
