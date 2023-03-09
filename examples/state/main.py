from beaker.client import ApplicationClient, LogicException
from beaker.sandbox import get_accounts, get_algod_client
from examples.state.contract import (
    app,
    get_global_state_val,
    get_local_state_val,
    get_reserved_global_state_val,
    get_reserved_local_state_val,
    incr_local_state_val,
    read_local_blob,
    set_global_state_val,
    set_local_state_val,
    set_reserved_global_state_val,
    set_reserved_local_state_val,
    write_global_blob,
    write_local_blob,
)


def demo() -> None:

    accts = get_accounts()

    acct = accts.pop()

    client = get_algod_client()

    app_client = ApplicationClient(client, app, signer=acct.signer)
    app_id, app_address, transaction_id = app_client.create()
    print(
        f"DEPLOYED: App ID: {app_id} Address: {app_address} "
        + f"Transaction ID: {transaction_id}"
    )

    app_client.opt_in()
    print("Opted in")

    app_client.call(set_local_state_val, v=123)
    app_client.call(incr_local_state_val, v=1)
    result = app_client.call(get_local_state_val)
    print(f"Set/get acct state result: {result.return_value}")

    app_client.call(set_reserved_local_state_val, k=123, v="stuff")
    result = app_client.call(get_reserved_local_state_val, k=123)
    print(f"Set/get dynamic acct state result: {result.return_value}")

    try:
        app_client.call(set_global_state_val, v="Expect fail")
    except LogicException as e:
        print(f"Task failed successfully: {e}")
    result = app_client.call(get_global_state_val)
    print(f"Set/get app state result: {result.return_value}")

    app_client.call(set_reserved_global_state_val, k=15, v=123)
    result = app_client.call(get_reserved_global_state_val, k=15)
    print(f"Set/get dynamic app state result: {result.return_value}")

    msg = "abc123"

    # Account state blob
    app_client.call(write_local_blob, v=msg)
    result = app_client.call(read_local_blob)
    got_msg = bytes(result.return_value[: len(msg)]).decode()
    assert msg == got_msg
    print(f"wrote and read the message to local state {got_msg}")

    # App state blob
    app_client.call(write_global_blob, v=msg)
    print("wrote message to global state")
    # result = app_client.call(read_global_blob)
    # got_msg = bytes(result.return_value[: len(msg)]).decode()
    # assert msg == got_msg
    # print(f"wrote and read the message to application state {got_msg}")


if __name__ == "__main__":
    demo()
