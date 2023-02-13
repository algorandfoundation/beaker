from pyteal import abi, TealType, Global, Int, Seq, Expr

from beaker import (
    sandbox,
    Application,
    Authorize,
    ApplicationStateValue,
    unconditional_create_approval,
)
from beaker.client import ApplicationClient, LogicException


class CounterState:
    counter = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )


counter_app = Application("CounterApp", state=CounterState()).implement(
    unconditional_create_approval, initialize_app_state=True
)


AuthorizeCreatorOnly = Authorize.only(Global.creator_address())


@counter_app.external(authorize=AuthorizeCreatorOnly)
def increment(*, output: abi.Uint64) -> Expr:
    """increment the counter"""
    return Seq(
        counter_app.state.counter.set(counter_app.state.counter + Int(1)),
        output.set(counter_app.state.counter),
    )


@counter_app.external(authorize=AuthorizeCreatorOnly)
def decrement(*, output: abi.Uint64) -> Expr:
    """decrement the counter"""
    return Seq(
        counter_app.state.counter.set(counter_app.state.counter - Int(1)),
        output.set(counter_app.state.counter),
    )


def demo() -> None:
    client = sandbox.get_algod_client()

    accts = sandbox.get_accounts()
    acct = accts.pop()

    # Create an Application client containing both an algod client and my app
    app_client = ApplicationClient(client, counter_app, signer=acct.signer)

    # Create the applicatiion on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    app_client.call("increment")
    app_client.call("increment")
    app_client.call("increment")
    result = app_client.call("increment")
    print(f"Currrent counter value: {result.return_value}")

    result = app_client.call("decrement")
    print(f"Currrent counter value: {result.return_value}")

    try:
        # Try to call the increment method with a different signer, it should fail
        # since we have the auth check
        other_acct = accts.pop()
        other_client = app_client.prepare(signer=other_acct.signer)
        other_client.call("increment")
    except LogicException as e:
        print("App call failed as expected.")
        print(e)


if __name__ == "__main__":
    demo()
