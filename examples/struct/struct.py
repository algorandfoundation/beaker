from typing import Final

from pyteal import *
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
)

from beaker import (
    Application,
    DynamicAccountStateValue,
    handler,
    sandbox,
    client,
    struct,
)


class Structer(Application):
    # Our custom model
    class Order(struct.Struct):
        item: abi.String
        quantity: abi.Uint16

    orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
    )

    @handler
    def place_order(self, order_number: abi.Uint8, order: Order):
        return self.orders[order_number].set(order.encode())

    @handler(read_only=True)
    def read_item(self, order_number: abi.Uint8, *, output: Order):
        return output.decode(self.orders[order_number])

    @handler
    def increase_quantity(self, order_number: abi.Uint8, *, output: Order):
        return Seq(
            # Read the order from state
            (new_order := Modeler.Order()).decode(self.orders[order_number]),
            # Select out in the quantity attribute, its a TupleElement type
            # so needs to be stored somewhere
            (quant := abi.Uint16()).set(new_order.quantity),
            # Add 1 to quantity
            quant.set(quant.get() + Int(1)),
            # We've gotta set all of the fields at the same time, but we can
            # borrow the item we already know about
            new_order.set(new_order.item, quant),
            # Write the new order to state
            self.orders[order_number].set(new_order.encode()),
            # Write new order to caller
            output.decode(new_order.encode()),
        )


def demo():
    addr, sk = sandbox.get_accounts().pop()
    signer = AccountTransactionSigner(sk)

    # Initialize Application from amm.py
    app = Structer()

    # Create an Application client containing both an algod client and my app
    app_client = client.ApplicationClient(sandbox.get_client(), app, signer=signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    app_client.opt_in()

    # Passing in a dict as an argument that should take a tuple according to the type spec
    order_number = 12
    order = {"quantity": 8, "item": "cubes"}
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
    print(f"Decoded result: {abi_decoded}")

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
