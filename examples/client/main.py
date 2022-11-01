from typing import Final
from pyteal import abi, TealType, Global, Approve
from beaker import (
    Application,
    AccountStateValue,
    ApplicationStateValue,
    Authorize,
    create,
    external,
    opt_in,
    close_out,
    delete,
    client,
    sandbox,
    consts,
)
from beaker.client.application_client import ApplicationClient
from beaker.client.logic_error import LogicException


class ClientExample(Application):
    manager: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, default=Global.creator_address()
    )

    nickname: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.bytes, descr="what this user prefers to be called"
    )

    @create
    def create(self):
        return self.initialize_application_state()

    @opt_in
    def opt_in(self):
        # Defaults to sender
        return self.initialize_account_state()

    @close_out
    def close_out(self):
        return Approve()

    @delete(authorize=Authorize.only(manager))
    def delete(self):
        return Approve()

    @external(authorize=Authorize.only(manager))
    def set_manager(self, new_manager: abi.Address):
        return self.manager.set(new_manager.get())

    @external
    def set_nick(self, nick: abi.String):
        return self.nickname.set(nick.get())

    @external(read_only=True)
    def get_nick(self, *, output: abi.String):
        return output.set(self.nickname)


def demo():
    # Set up accounts we'll use
    accts = sandbox.get_accounts()

    acct1 = accts.pop()
    acct2 = accts.pop()

    # Create Application client
    app_client1 = client.ApplicationClient(
        client=sandbox.get_algod_client(), app=ClientExample(), signer=acct1.signer
    )

    # Create the app on-chain (uses signer1)
    app_client1.create()
    print(f"Current app state: {app_client1.get_application_state()}")
    # Fund the app account with 1 algo
    app_client1.fund(1 * consts.algo)

    # Try calling set nickname from both accounts after opting in
    app_client1.opt_in()
    app_client1.call(ClientExample.set_nick, nick="first")

    print(f"Current app state: {app_client1.get_application_state()}")
    # Create copies of the app client with specific signer, _after_ we've created and set the app id
    app_client2 = app_client1.prepare(signer=acct2.signer)
    print(f"Current app state: {app_client1.get_application_state()}")

    # Try calling without opting in
    try:
        app_client2.call(ClientExample.set_nick, nick="second")
    except LogicException as e:
        print(f"\n{e}\n")

    app_client2.opt_in()
    app_client2.call(ClientExample.set_nick, nick="second")

    # Get the local state for each account
    print(app_client1.get_account_state())
    print(app_client2.get_account_state())

    # Get the global state
    print(f"Current app state: {app_client1.get_application_state()}")

    try:
        app_client2.call(ClientExample.set_manager, new_manager=acct2.address)
        print("Shouldn't get here")
    except LogicException as e:
        print("Failed as expected, only addr1 should be authorized to set the manager")
        print(f"\n{e}\n")

    # Have addr1 set the manager to addr2
    app_client1.call(ClientExample.set_manager, new_manager=acct2.address)
    print(f"Current app state: {app_client1.get_application_state()}")

    print(app_client1.get_application_state())
    # and back
    app_client2.call(ClientExample.set_manager, new_manager=acct1.address)
    print(f"Current app state: {app_client1.get_application_state()}")

    ## Create a new client that just sets the app id we wish to interact with
    app_client3 = ApplicationClient(
        client=sandbox.get_algod_client(),
        app=ClientExample(),
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
    demo()
