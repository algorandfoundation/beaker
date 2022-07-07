from algosdk.v2client.algod import AlgodClient

DEFAULT_ALGOD_ADDRESS = "http://localhost:4001"
DEFAULT_ALGOD_TOKEN = "a" * 64


def get_client(address: str = DEFAULT_ALGOD_ADDRESS, token: str = DEFAULT_ALGOD_TOKEN):
    return AlgodClient(token, address)
