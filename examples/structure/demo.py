from algosdk.abi import ABIType

from beaker import client, sandbox

from examples.structure import structer


def main() -> None:
    # Create a codec from the python sdk
    order_codec = ABIType.from_string(str(structer.Order().type_spec()))

    acct = sandbox.get_accounts().pop()

    # Create an Application client containing both an algod client and my app
    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), structer.app, signer=acct.signer
    )

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    # Since we're using local state, opt in
    app_client.opt_in()

    # Passing in a dict as an argument that should take a tuple
    # according to the type spec
    order_number = 12
    order = {"quantity": 8, "item": "cubes"}
    app_client.call(structer.place_order, order_number=order_number, order=order)

    # Get the order from the state field
    state_key = order_number.to_bytes(1, "big")
    stored_order = app_client.get_local_state(raw=True)[state_key]
    assert isinstance(stored_order, bytes)
    state_decoded = order_codec.decode(stored_order)

    print(
        "We can get the order we stored from local "
        f"state of the sender: {state_decoded}"
    )

    # Or we could call the read-only method, passing the order number
    result = app_client.call(structer.read_item, order_number=order_number)
    abi_decoded = order_codec.decode(result.raw_value)
    print(f"Decoded result: {abi_decoded}")

    # Update the order to increase the quantity
    result = app_client.call(structer.increase_quantity, order_number=order_number)
    increased_decoded = order_codec.decode(result.raw_value)
    print(
        "Let's add 1 to the struct, update state, and "
        f"return the updated version: {increased_decoded}"
    )

    # And read it back out from state
    state_key = order_number.to_bytes(1, "big")
    stored_order = app_client.get_local_state(raw=True)[state_key]
    assert isinstance(stored_order, bytes)
    state_decoded = order_codec.decode(stored_order)
    print(f"And it's been updated: {state_decoded}")


if __name__ == "__main__":
    main()
