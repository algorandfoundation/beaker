import json

from algosdk.abi import ABIType

from beaker import client, sandbox

from examples.wormhole import oracle

base_vaa = bytes.fromhex(
    "010000000001008049340af360a47103a962108cb57b9deebcc99e8e6ddeca1a"
    + "1fb025413a62ac2cae4abd6b7e0ce7fc5a6bc99536387a3827cbbb0c710c81213"
    + "a417cb59b89de01630d06ae0000000000088edf5b0e108c3a1a0a4b704cc89591"
    + "f2ad8d50df24e991567e640ed720a94be20000000000000004000300000000000"
    + "00000000000000000000000000000000000000000000000000064000000000000"
    + "0000000000000000000000000000000000000000000000000000000f6463fab1a"
    + "45027a3c70781ae588e4e6661d21a7c19535a5d6b4f4c3164a13be1000f0b7ef3"
    + "fcf3f8d9efc458695dc7bd7e534080ac7b48f2b881fd3063b1308f0648"
)

# Get the codec to decode the stored value
oracle_data_codec = ABIType.from_string(str(oracle.OracleData().type_spec()))


def main() -> None:
    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        oracle.app,
        signer=sandbox.get_accounts().pop().signer,
    )

    # Deploy the app on chain
    app_client.create()

    # Make up some fake oracle data and send it to the contract
    base_ts = 1661802300
    base_price = 10000
    for x in range(10):
        fauxracle_data = {
            "ts": base_ts + x * 60,
            "price": base_price + x,
            "confidence": 9999,
        }

        app_client.call(
            "portal_transfer",
            vaa=base_vaa + json.dumps(fauxracle_data).encode(),
        )

    # Get the current app state
    global_state = app_client.get_global_state(raw=True)
    for v in global_state.values():
        assert isinstance(v, bytes)
        ts, price, confidence = oracle_data_codec.decode(v)
        print(f"ts: {ts}, price: {price}, confidence: {confidence}")


if __name__ == "__main__":
    main()
