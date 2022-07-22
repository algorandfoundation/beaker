from pyteal import *
from beaker import *

# Create a class, subclassing Application from beaker
class MySickApp(Application):

    # Add a method handler, ABI method string will be `hello(string)string`
    @handler
    def hello(name: abi.String, *, output: abi.String):
        # Return the result of `Hello, `+name
        return output.set(Concat(Bytes("Hello, "), name.get()))

if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import AccountTransactionSigner
    from beaker import sandbox, client

    # Instantiate our app
    msa = MySickApp()

    # Get an acct from the sandbox
    addr, secret = sandbox.get_accounts().pop()
    signer = AccountTransactionSigner(secret)

    # Create an Application client for calls
    app_client = client.ApplicationClient(sandbox.get_client(), msa, signer=signer)

    # Deploy the app
    app_id, app_addr, txid = app_client.create()

    # Call the method we defined
    result = app_client.call(msa.hello, name="Beaker")
    print(result.return_value) # Hello, Beaker