from pyteal import abi
from beaker import sandbox, client, Application


external_example_app = Application("ExternalExample")


@external_example_app.create
def create(input: abi.String, *, output: abi.String):
    return output.decode(input.encode())


def demo():

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        external_example_app,
        signer=sandbox.get_accounts().pop().signer,
    )
    app_client.create(input="yo")
    # print(result.return_value)


if __name__ == "__main__":
    demo()
