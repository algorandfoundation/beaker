from typing import Final

from beaker.client import ApplicationClient, LogicException
from beaker import sandbox

from pyteal import abi, TealType, Global, Int, Seq
from beaker.application import Application
from beaker.state import ApplicationStateValue
from beaker.decorators import external, create, Authorize


class CounterApp(Application):

    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )

    # Note: this method is redundant with the one defined in Application
    # defining it here to demonstrate functionality
    @create
    def create(self):
        """create application"""
        return self.initialize_application_state()

    @external(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        """increment the counter"""
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def decrement(self, *, output: abi.Uint64):
        """decrement the counter"""
        return Seq(
            self.counter.set(self.counter - Int(1)),
            output.set(self.counter),
        )


def demo():
    client = sandbox.get_algod_client()

    accts = sandbox.get_accounts()
    acct = accts.pop()

    # Initialize Application from amm.py
    app = CounterApp()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, app, signer=acct.signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    app_client.call(app.increment)
    app_client.call(app.increment)
    app_client.call(app.increment)
    result = app_client.call(app.increment)
    print(f"Currrent counter value: {result.return_value}")

    result = app_client.call(app.decrement)
    print(f"Currrent counter value: {result.return_value}")

    try:
        # Try to call the increment method with a different signer, it should fail
        # since we have the auth check
        other_acct = accts.pop()
        other_client = app_client.prepare(signer=other_acct.signer)
        other_client.call(app.increment)
    except LogicException as e:
        print("App call failed as expected.")
        print(e)


if __name__ == "__main__":
    ca = CounterApp()
    demo()
