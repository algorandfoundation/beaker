from dataclasses import dataclass
from hashlib import sha256
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    TransactionWithSigner,
)
from algosdk.future import transaction

import algosdk.abi as sdk_abi
from beaker.client import ApplicationClient
from beaker.sandbox import get_client, get_accounts

from contract import Modeler


client = get_client()

addr, sk = get_accounts()[0]
signer = AccountTransactionSigner(sk)

# Initialize Application from amm.py
app = Modeler()

# Create an Application client containing both an algod client and my app
sp = client.suggested_params()
app_client = ApplicationClient(client, app, signer=signer, suggested_params=sp)


def demo():

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    app_client.opt_in()

    order_number = 12
    order = {"quantity": 8, "item": "cubes"}
    # Passing in a dict as an argument that should take a tuple according to the
    # type spec
    app_client.call(app.place_order, order_number=order_number, order=order)

    state_key = order_number.to_bytes(1, "big")
    stored_order = app_client.get_account_state()[state_key]
    state_decoded = Modeler.Order().client_decode(stored_order)
    print(
        f"We can get the order we stored from local state of the sender: {state_decoded}"
    )

    # Or we could
    result = app_client.call(app.read_item, order_number=order_number)
    abi_decoded = Modeler.Order().client_decode(result.raw_value)
    print(f"We can provide a method to read it: {abi_decoded}")

    result = app_client.call(app.increase_quantity, order_number=order_number)
    increased_decoded = Modeler.Order().client_decode(result.raw_value)
    print(
        f"Let's add 1 to model, update state, and return the updated version: {increased_decoded}"
    )

    state_key = order_number.to_bytes(1, "big")
    stored_order = app_client.get_account_state()[state_key]
    state_decoded = Modeler.Order().client_decode(stored_order)
    print(f"And it's been updated: {state_decoded}")


if __name__ == "__main__":
    demo()
