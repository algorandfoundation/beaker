import pyteal as pt

from beaker import Application, client, localnet

external_example_app = Application("ExternalExample")


@external_example_app.create
def create(input: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return output.decode(input.encode())


def demo() -> None:

    app_client = client.ApplicationClient(
        localnet.get_algod_client(),
        external_example_app,
        signer=localnet.get_accounts().pop().signer,
    )
    app_client.create(input="yo")
    # print(result.return_value)


if __name__ == "__main__":
    demo()
