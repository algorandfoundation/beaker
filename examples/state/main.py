from beaker.client import ApplicationClient, LogicException
from beaker.sandbox import get_algod_client, get_accounts

# Leet hax, ignore
if __name__ == "__main__":
    from contract import StateExample
else:
    from .contract import StateExample


def demo():

    accts = get_accounts()

    acct = accts.pop()

    client = get_algod_client()

    app_client = ApplicationClient(client, StateExample(), signer=acct.signer)
    app_id, app_address, transaction_id = app_client.create()
    print(
        f"DEPLOYED: App ID: {app_id} Address: {app_address} Transaction ID: {transaction_id}"
    )

    app_client.opt_in()
    print("Opted in")

    app_client.call(StateExample.set_account_state_val, v=123)
    app_client.call(StateExample.incr_account_state_val, v=1)
    result = app_client.call(StateExample.get_account_state_val)
    print(f"Set/get acct state result: {result.return_value}")

    app_client.call(StateExample.set_dynamic_account_state_val, k=0, v="stuff")
    result = app_client.call(StateExample.get_dynamic_account_state_val, k=0)
    print(f"Set/get dynamic acct state result: {result.return_value}")

    try:
        app_client.call(StateExample.set_app_state_val, v="Expect fail")
    except LogicException as e:
        print(f"Task failed successfully: {e}")
        result = app_client.call(StateExample.get_app_state_val)
        print(f"Set/get app state result: {result.return_value}")

    app_client.call(StateExample.set_dynamic_app_state_val, k=15, v=123)
    result = app_client.call(StateExample.get_dynamic_app_state_val, k=15)
    print(f"Set/get dynamic app state result: {result.return_value}")


if __name__ == "__main__":
    demo()
