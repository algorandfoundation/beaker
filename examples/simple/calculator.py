from pyteal import abi

from beaker import sandbox
from beaker.client import ApplicationClient
from beaker.testing.legacy import LegacyApplication


class Calculator(LegacyApplication):
    def post_init(self) -> None:
        @self.external
        def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            """Add a and b, return the result"""
            return output.set(a.get() + b.get())

        @self.external
        def mul(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            """Multiply a and b, return the result"""
            return output.set(a.get() * b.get())

        @self.external
        def sub(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            """Subtract b from a, return the result"""
            return output.set(a.get() - b.get())

        @self.external
        def div(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            """Divide a by b, return the result"""
            return output.set(a.get() / b.get())


def demo():
    # Here we use `sandbox` but beaker.client.api_providers can also be used
    # with something like ``AlgoNode(Network.TestNet).algod()``
    algod_client = sandbox.get_algod_client()

    acct = sandbox.get_accounts().pop()

    # Create an Application client containing both an algod client and app
    app_client = ApplicationClient(
        client=algod_client, app=Calculator(), signer=acct.signer
    )

    # Create the application on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    result = app_client.call("add", a=2, b=2)
    print(f"add result: {result.return_value}")

    result = app_client.call("mul", a=2, b=2)
    print(f"mul result: {result.return_value}")

    result = app_client.call("sub", a=6, b=2)
    print(f"sub result: {result.return_value}")

    result = app_client.call("div", a=16, b=4)
    print(f"div result: {result.return_value}")


if __name__ == "__main__":
    import json

    calc = Calculator()
    print(calc.approval_program)
    print(calc.clear_program)
    assert calc.contract
    print(json.dumps(calc.contract.dictify()))

    demo()
