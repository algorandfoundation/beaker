from typing import Final
from algosdk.atomic_transaction_composer import AccountTransactionSigner
from pyteal import *
from beaker import (
    Application,
    AccountStateValue,
    ApplicationStateValue,
    Authorize,
    external,
    client,
    sandbox,
)


class ClientExample(Application):
    manager: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, default=Global.creator_address()
    )

    nickname: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.bytes, descr="what this user prefers to be called"
    )

    @external(authorize=Authorize.only(manager))
    def set_manager(self, new_manager: abi.Address):
        return self.manager.set(new_manager.get())

    @external
    def set_nick(self, nick: abi.String):
        return self.nickname.set(nick.get())


def demo():

    # Set up accounts we'll use
    accts = sandbox.get_accounts()

    addr1, sk1 = accts.pop()
    signer1 = AccountTransactionSigner(sk1)

    addr2, sk2 = accts.pop()
    signer2 = AccountTransactionSigner(sk2)

    # Instantiate app
    app = ClientExample()

    # Create Application client
    app_client = client.ApplicationClient(client=sandbox.get_client(), app=app)

    # Create the app on chain using signer1
    app_id, app_addr, txid = app_client.create(signer=signer1)

    # Create copies of the app client with specific signer, _after_ we've created and set the app id
    app_client1 = app_client.prepare(signer=signer1)
    app_client2 = app_client.prepare(signer=signer2)

    # Try calling set nickname from both accounts after opting in
    app_client1.opt_in()
    app_client1.call(app.set_nick, nick="first")

    app_client2.opt_in()
    app_client2.call(app.set_nick, nick="second")

    # Get the local state for each account
    print(app_client1.get_account_state(force_str=True))

    print(app_client2.get_account_state(force_str=True))

    # Get the global state
    print(f"Current app state: {app_client.get_application_state(force_str=True)}")

    try:
        app_client2.call(app.set_manager, new_manager=addr2)
        print("Shouldn't get here")
    except Exception as e:
        print()
        print(app_client2.parse_logic_error(str(e)))
        print()
        print("Failed as expected, only addr1 should be authorized to set the manager")

    # Have addr1 set the manager to addr2
    app_client1.call(app.set_manager, new_manager=addr2)
    print(f"Current app state: {app_client.get_application_state(force_str=True)}")

    # and back
    app_client2.call(app.set_manager, new_manager=addr1)
    print(f"Current app state: {app_client.get_application_state(force_str=True)}")


if __name__ == "__main__":
    demo()
