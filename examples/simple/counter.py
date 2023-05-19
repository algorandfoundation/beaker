import pyteal as pt
from algokit_utils import LogicError

from beaker import (
    Application,
    Authorize,
    GlobalStateValue,
    localnet,
)
from beaker.client import ApplicationClient


class CounterState:
    counter = GlobalStateValue(
        stack_type=pt.TealType.uint64,
        descr="A counter for showing how to use application state",
    )


counter_app = Application("CounterApp", state=CounterState())


@counter_app.external(authorize=Authorize.only_creator())
def increment(*, output: pt.abi.Uint64) -> pt.Expr:
    """increment the counter"""
    return pt.Seq(
        counter_app.state.counter.set(counter_app.state.counter + pt.Int(1)),
        output.set(counter_app.state.counter),
    )


@counter_app.external(authorize=Authorize.only_creator())
def decrement(*, output: pt.abi.Uint64) -> pt.Expr:
    """decrement the counter"""
    return pt.Seq(
        counter_app.state.counter.set(counter_app.state.counter - pt.Int(1)),
        output.set(counter_app.state.counter),
    )


def demo() -> None:
    client = localnet.get_algod_client()

    accts = localnet.get_accounts()
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
