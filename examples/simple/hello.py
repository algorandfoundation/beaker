from pyteal import *
from beaker import *

# Create a class, subclassing Application from beaker
class HelloBeaker(Application):
    # Add an external method with ABI method signature `hello(string)string`
    @external
    def hello(self, name: abi.String, *, output: abi.String):
        # Set output to the result of `Hello, `+name
        return output.set(Concat(Bytes("Hello, "), name.get()))


def demo():
    # Create an Application client
    app_client = client.ApplicationClient(
        # Get sandbox algod client
        client=sandbox.get_algod_client(),
        # Instantiate app with the program version (default is MAX_TEAL_VERSION)
        app=HelloBeaker(version=6),
        # Get acct from sandbox and pass the signer
        signer=sandbox.get_accounts().pop().signer,
    )

    # Deploy the app on-chain
    app_id, app_addr, txid = app_client.create()
    print(
        f"""Deployed app in txid {txid}
        App ID: {app_id} 
        Address: {app_addr} 
    """
    )

    # Call the `hello` method
    result = app_client.call(HelloBeaker.hello, name="Beaker")
    print(result.return_value)  # "Hello, Beaker"


if __name__ == "__main__":
    demo()
