from beaker.client import ApplicationClient, LogicException
from beaker.sandbox import get_algod_client, get_accounts

# Leet hax, ignore
if __name__ == "__main__":
    from contract import StateExample  # type: ignore
else:
    from .contract import StateExample


def demo():

    accts = get_accounts()

    acct = accts.pop()

    client = get_algod_client()

    app = StateExample()

    app_client = ApplicationClient(client, StateExample(), signer=acct.signer)
    app_id, app_address, transaction_id = app_client.create()
    print(
        f"DEPLOYED: App ID: {app_id} Address: {app_address} "
        + f"Transaction ID: {transaction_id}"
    )

    app_client.opt_in()
    print("Opted in")

    app_client.call("set_account_state_val", v=123)
    app_client.call("incr_account_state_val", v=1)
    result = app_client.call("get_account_state_val")
    print(f"Set/get acct state result: {result.return_value}")

    app_client.call("set_reserved_account_state_val", k=123, v="stuff")
    result = app_client.call("get_reserved_account_state_val", k=123)
    print(f"Set/get dynamic acct state result: {result.return_value}")

    try:
        app_client.call("set_app_state_val", v="Expect fail")
    except LogicException as e:
        print(f"Task failed successfully: {e}")
        result = app_client.call("get_app_state_val")
        print(f"Set/get app state result: {result.return_value}")

    app_client.call("set_reserved_app_state_val", k=15, v=123)
    result = app_client.call("get_reserved_app_state_val", k=15)
    print(f"Set/get dynamic app state result: {result.return_value}")

    msg = "write this message please and make it readable"

    # Account state blob
    app_client.call("write_acct_blob", v=msg)
    result = app_client.call("read_acct_blob")
    got_msg = bytes(result.return_value[: len(msg)]).decode()
    assert msg == got_msg
    print(f"wrote and read the message to account state {got_msg}")

    # App state blob
    app_client.call("write_app_blob", v=msg)
    # result = app_client.call("read_app_blob")
    # got_msg = bytes(result.return_value[: len(msg)]).decode()
    # assert msg == got_msg
    print(f"wrote and read the message to application state {got_msg}")


if __name__ == "__main__":
    demo()
