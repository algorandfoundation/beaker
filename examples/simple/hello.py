from pyteal import Concat, Bytes, Expr, abi
from beaker import sandbox, client, Application
from beaker.application import CompilerOptions

# Create a class, subclassing Application from beaker
class HelloBeaker(Application):
    pass


hello_app = HelloBeaker(compiler_options=CompilerOptions(avm_version=8))


@hello_app.external
def hello(name: abi.String, *, output: abi.String) -> Expr:
    # Set output to the result of `Hello, `+name
    return output.set(Concat(Bytes("Hello, "), name.get()))


def demo():
    # Create an Application client
    app_client = client.ApplicationClient(
        # Get sandbox algod client
        client=sandbox.get_algod_client(),
        # Instantiate app with the program version (default is MAX_TEAL_VERSION)
        app=hello_app,
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
    result = app_client.call(hello, name="Beaker")
    print(result.return_value)  # "Hello, Beaker"


if __name__ == "__main__":
    demo()
