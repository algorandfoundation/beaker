from pyteal import *
from beaker import *

# Create a class, subclassing Application from beaker
class HelloBeaker(Application):

    # Add an external method, ABI method signature will be `hello(string)string`
    @external
    def hello(self, name: abi.String, *, output: abi.String):
        # Return the result of `Hello, `+name
        return output.set(Concat(Bytes("Hello, "), name.get()))


if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import AccountTransactionSigner
    from beaker import sandbox, client

    # Instantiate our app
    app = HelloBeaker()

    # Get an acct from the sandbox
    addr, secret = sandbox.get_accounts().pop()

    # Create an Application client
    app_client = client.ApplicationClient(
        client=sandbox.get_client(), app=app, signer=AccountTransactionSigner(secret)
    )

    # Deploy the app
    app_id, app_addr, txid = app_client.create()

    # Call the method we defined
    result = app_client.call(app.hello, name="Beaker")
    print(result.return_value)  # Hello, Beaker
