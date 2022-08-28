from pyteal import *
from beaker import *


class ExternalExample(Application):
    @create
    def create(self, input: abi.String, *, output: abi.String):
        return output.decode(input.encode())


def demo():

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        ExternalExample(),
        signer=sandbox.get_accounts().pop().signer,
    )
    app_client.create(input="yo")
    # print(result.return_value)


if __name__ == "__main__":
    demo()
