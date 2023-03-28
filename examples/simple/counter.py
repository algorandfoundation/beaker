from algokit_utils import LogicError
from pyteal import Expr, Int, Seq, TealType, abi

from beaker import (
    Application,
    Authorize,
    GlobalStateValue,
    sandbox,
)
from beaker.client import ApplicationClient


class CounterState:
    counter = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )


counter_app = Application("CounterApp", state=CounterState())


@counter_app.external(authorize=Authorize.only_creator())
def increment(*, output: abi.Uint64) -> Expr:
    """increment the counter"""
    return Seq(
        counter_app.state.counter.set(counter_app.state.counter + Int(1)),
        output.set(counter_app.state.counter),
    )


@counter_app.external(authorize=Authorize.only_creator())
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

    app_client.call(increment)
    app_client.call(increment)
    app_client.call(increment)
    result = app_client.call(increment)
    print(f"Currrent counter value: {result.return_value}")

    result = app_client.call(decrement)
    print(f"Currrent counter value: {result.return_value}")

    try:
        # Try to call the increment method with a different signer, it should fail
        # since we have the auth check
        other_acct = accts.pop()
        other_client = app_client.prepare(signer=other_acct.signer)
        other_client.call(increment)
    except LogicError as e:
        print(e)
        print("App call failed as expected.")


if __name__ == "__main__":
    demo()
