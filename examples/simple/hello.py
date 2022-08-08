from pyteal import abi, Concat, Bytes
from beaker import Application, external

# Create a class, subclassing Application from beaker
class HelloBeaker(Application):

    # Add an external method with ABI method signature `hello(string)string`
    @external
    def hello(self, name: abi.String, *, output: abi.String):
        # Set output to the result of `Hello, `+name
        return output.set(Concat(Bytes("Hello, "), name.get()))


if __name__ == "__main__":
    from beaker import sandbox, client

    # Instantiate our app
    app = HelloBeaker()

    # Get an acct from the sandbox
    acct = sandbox.get_accounts().pop()

    # Create an Application client
    app_client = client.ApplicationClient(
        client=sandbox.get_algod_client(), app=app, signer=acct.signer
    )

    # Deploy the app
    app_id, app_addr, txid = app_client.create()
    print(f"Deployed app with id {app_id} and address {app_addr} in txid {txid}")

    # Call the `hello` method
    result = app_client.call(app.hello, name="Beaker")
    assert result.return_value == "Hello, Beaker"
