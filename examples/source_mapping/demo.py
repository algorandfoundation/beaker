from beaker import client, sandbox

from examples.source_mapping.app import add, source_mapped_app


def main() -> None:
    ac = sandbox.get_algod_client()
    acct = sandbox.get_accounts().pop()

    app_spec = source_mapped_app.build(ac)

    # write out programs to disk
    app_spec.export("SourceMap.artifacts")

    app_client = client.ApplicationClient(client=ac, app=app_spec, signer=acct.signer)
    # deploy app
    app_client.create()

    # trigger assert
    try:
        app_client.call(add, a=11, b=42)
    except Exception as e:
        print("Got expected exception:\n", e)


if __name__ == "__main__":
    main()
