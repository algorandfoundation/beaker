from beaker import client, sandbox

from examples.blueprint import app


def main() -> None:
    app_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=app.extended_app,
        signer=sandbox.get_accounts().pop().signer,
    )

    # Deploy the app on-chain
    app_client.create()

    # Call the `sum` method we added with the blueprint
    result = app_client.call("add", a=1, b=2)
    print(result.return_value)  # 3

    # Call the `div` method we added with the blueprint
    result = app_client.call("div", a=6, b=2)
    print(result.return_value)  # 3


if __name__ == "__main__":
    main()
