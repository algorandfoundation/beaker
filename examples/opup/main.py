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
    result = app_client.call(app.bootstrap, ptxn=txn)
    oua = result.abi_results[0].return_value
    print(f"Created op up app: {oua}")

    input = "stuff"
    iters = 10

    # Passing None for the app id forces the ApplicationClient to try and resolve it
    # TODO: make args => kwargs so we can be more explicit about the args passed and
    # what their value should be.

    # consider app_id=ResolveHint()
    result = app_client.call(app.hash_it, input=input, iters=iters)

    # Get the first result and trim off str encoding bytes, I should have used byte[32]
    result_hash = result.abi_results[0].raw_value[2:]

    local_hash = input.encode()
    for _ in range(iters):
        local_hash = sha256(local_hash).digest()

    assert result_hash == local_hash, f"Expected {local_hash} got {result_hash}"

    print(f"Successfully hashed {input},  {iters} times to produce {result_hash.hex()}")


if __name__ == "__main__":
    demo()
