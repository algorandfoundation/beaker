from algokit_utils import LogicError

from beaker import client, consts, sandbox
from beaker.client import ApplicationClient

from examples.client import nicknames


def main() -> None:
    # Set up accounts we'll use
    accts = sandbox.get_accounts()

    acct1 = accts.pop()
    acct2 = accts.pop()

    # Create Application client
    app_client1 = client.ApplicationClient(
        client=sandbox.get_algod_client(), app=nicknames.app, signer=acct1.signer
    )

    # Create the app on-chain (uses signer1)
    app_id, app_addr, txid = app_client1.create()
    print(f"Created app with id {app_id} and address {app_addr} in transaction {txid}")

    print(f"Current app state: {app_client1.get_global_state()}")
    # Fund the app account with 1 algo
    app_client1.fund(1 * consts.algo)

    # Try calling set nickname from both accounts after opting in
    app_client1.opt_in()
    app_client1.call(nicknames.set_nick, nick="first")

    print(f"Current app state: {app_client1.get_global_state()}")
    # Create copies of the app client with specific signer, _after_ we've created and set the app id
    app_client2 = app_client1.prepare(signer=acct2.signer)
    print(f"Current app state: {app_client1.get_global_state()}")

    # Try calling without opting in
    try:
        app_client2.call(nicknames.set_nick, nick="second")
    except LogicError as e:
        print(f"\n{e}\n")

    app_client2.opt_in()
    app_client2.call(nicknames.set_nick, nick="second")

    # Get the local state for each account
    print(app_client1.get_local_state())
    print(app_client2.get_local_state())

    # Get the global state
    print(f"Current app state: {app_client1.get_global_state()}")

    try:
        app_client2.call(nicknames.set_manager, new_manager=acct2.address)
        print("Shouldn't get here")
    except LogicError as e:
        print("Failed as expected, only addr1 should be authorized to set the manager")
        print(f"\n{e}\n")

    # Have addr1 set the manager to addr2
    app_client1.call(nicknames.set_manager, new_manager=acct2.address)
    print(f"Current app state: {app_client1.get_global_state()}")

    print(app_client1.get_global_state())
    # and back
    app_client2.call(nicknames.set_manager, new_manager=acct1.address)
    print(f"Current app state: {app_client1.get_global_state()}")

    # Create a new client that just sets the app id we wish to interact with
    app_client3 = ApplicationClient(
        client=sandbox.get_algod_client(),
        app=nicknames.app,
        signer=acct1.signer,
        app_id=app_client1.app_id,
    )

    try:
        app_client1.close_out()
        app_client2.close_out()
        app_client3.delete()
    except Exception as e:
        print(e)


if __name__ == "__main__":
    main()
