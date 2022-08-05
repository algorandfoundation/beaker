from pyteal import *
from algosdk.atomic_transaction_composer import AccountTransactionSigner

from beaker.client import ApplicationClient
from beaker.application import Application
from beaker.decorators import external
from beaker import sandbox


class Calculator(Application):
    @external
    def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        """Add a and b, return the result"""
        return output.set(a.get() + b.get())

    @external
    def mul(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        """Multiply a and b, return the result"""
        return output.set(a.get() * b.get())

    @external
    def sub(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        """Subtract b from a, return the result"""
        return output.set(a.get() - b.get())

    @external
    def div(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        """Divide a by b, return the result"""
        return output.set(a.get() / b.get())


def demo():
    client = sandbox.get_algod_client()

    addr, sk, signer = sandbox.get_accounts().pop()

    # Initialize Application
    app = Calculator()

    # Create an Application client containing both an algod client and app
    app_client = ApplicationClient(client=client, app=app, signer=signer)

    # Create the application on chain, set the app id for the app client
    app_id, app_addr, txid = app_client.create()
    print(f"Created App with id: {app_id} and address addr: {app_addr} in tx: {txid}")

    result = app_client.call(app.add, a=2, b=2)
    print(f"add result: {result.return_value}")

    result = app_client.call(app.mul, a=2, b=2)
    print(f"mul result: {result.return_value}")

    result = app_client.call(app.sub, a=6, b=2)
    print(f"sub result: {result.return_value}")

    result = app_client.call(app.div, a=16, b=4)
    print(f"div result: {result.return_value}")


if __name__ == "__main__":
    import json

    calc = Calculator()
    print(calc.approval_program)
    print(calc.clear_program)
    print(json.dumps(calc.contract.dictify()))

    demo()
