import pyteal as pt

from beaker import (
    Application,
    client,
    sandbox,
)

hello_app = Application("HelloBeaker")


@hello_app.external
def hello(name: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    # Set output to the result of `Hello, `+name
    return output.set(pt.Concat(pt.Bytes("Hello, "), name.get()))


def demo() -> None:
    # Create an Application client
    app_client = client.ApplicationClient(
        # Get sandbox algod client
        client=sandbox.get_algod_client(),
        # Pass instance of app to client
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
