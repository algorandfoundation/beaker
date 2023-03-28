from algokit_utils import LogicError

from beaker import client, sandbox

from examples.state import contract


def main() -> None:
    accts = sandbox.get_accounts()

    acct = accts.pop()

    algod_client = sandbox.get_algod_client()

    app_client = client.ApplicationClient(
        algod_client, contract.app, signer=acct.signer
    )
    app_id, app_address, transaction_id = app_client.create()
    print(
        f"DEPLOYED: App ID: {app_id} Address: {app_address} "
        + f"Transaction ID: {transaction_id}"
    )

    app_client.opt_in()
    print("Opted in")

    app_client.call(contract.set_local_state_val, v=123)
    app_client.call(contract.incr_local_state_val, v=1)
    result = app_client.call(contract.get_local_state_val)
    print(f"Set/get acct state result: {result.return_value}")

    app_client.call(contract.set_reserved_local_state_val, k=123, v="stuff")
    result = app_client.call(contract.get_reserved_local_state_val, k=123)
    print(f"Set/get dynamic acct state result: {result.return_value}")

    try:
        app_client.call(contract.set_global_state_val, v="Expect fail")
    except LogicError as e:
        print(f"Task failed successfully: {e}")
    result = app_client.call(contract.get_global_state_val)
    print(f"Set/get app state result: {result.return_value}")

    app_client.call(contract.set_reserved_global_state_val, k=15, v=123)
    result = app_client.call(contract.get_reserved_global_state_val, k=15)
    print(f"Set/get dynamic app state result: {result.return_value}")

    msg = "abc123"

    # Account state blob
    app_client.call(contract.write_local_blob, v=msg)
    result = app_client.call(contract.read_local_blob)
    got_msg = bytes(result.return_value[: len(msg)]).decode()
    assert msg == got_msg
    print(f"wrote and read the message to local state {got_msg}")

    # App state blob
    app_client.call(contract.write_global_blob, v=msg)
    print("wrote message to global state")
    # result = app_client.call(read_global_blob)
    # got_msg = bytes(result.return_value[: len(msg)]).decode()
    # assert msg == got_msg
    # print(f"wrote and read the message to application state {got_msg}")


if __name__ == "__main__":
    main()
