from pyteal import Expr, abi

from beaker import Application, sandbox
from beaker.client import ApplicationClient

calculator_app = Application("Calculator")


@calculator_app.external
def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
    """Add a and b, return the result"""
    return output.set(a.get() + b.get())


@calculator_app.external
def mul(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
    """Multiply a and b, return the result"""
    return output.set(a.get() * b.get())


@calculator_app.external
def sub(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
    """Subtract b from a, return the result"""
    return output.set(a.get() - b.get())


@calculator_app.external
def div(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
    """Divide a by b, return the result"""
    return output.set(a.get() / b.get())


def demo() -> None:
    # Here we use `sandbox` but beaker.client.api_providers can also be used
    # with something like ``AlgoNode(Network.TestNet).algod()``
    algod_client = sandbox.get_algod_client()

    acct = sandbox.get_accounts().pop()

    # Create an Application client containing both an algod client and app
    app_client = ApplicationClient(
        client=algod_client, app=calculator_app, signer=acct.signer
    )

    # Create the application on chain, implicitly sets the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    result = app_client.call(add, a=2, b=2)
    print(f"add result: {result.return_value}")

    result = app_client.call(mul, a=2, b=2)
    print(f"mul result: {result.return_value}")

    result = app_client.call(sub, a=6, b=2)
    print(f"sub result: {result.return_value}")

    result = app_client.call(div, a=16, b=4)
    print(f"div result: {result.return_value}")


if __name__ == "__main__":

    calc_app_spec = calculator_app.build()
    print(calc_app_spec.approval_program)
    print(calc_app_spec.clear_program)
    print(calc_app_spec.to_json())

    demo()
