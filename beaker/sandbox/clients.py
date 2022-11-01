from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

DEFAULT_ALGOD_ADDRESS = "http://localhost:4001"
DEFAULT_ALGOD_TOKEN = "a" * 64

DEFAULT_INDEXER_ADDRESS = "http://localhost:8980"
DEFAULT_INDEXER_TOKEN = "a" * 64


def get_algod_client(
    address: str = DEFAULT_ALGOD_ADDRESS, token: str = DEFAULT_ALGOD_TOKEN
) -> AlgodClient:
    """creates a new algod client using the default sandbox parameters"""
    return AlgodClient(token, address)


def get_indexer_client(
    address: str = DEFAULT_INDEXER_ADDRESS, token: str = DEFAULT_INDEXER_TOKEN
) -> IndexerClient:
    """creates a new indexer client using the default sandbox parameters"""
    return IndexerClient(token, address)
