from enum import Enum
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient


class Network(Enum):
    """Provides consistent way to reference the most common network options"""

    MainNet = "MainNet"
    TestNet = "TestNet"
    BetaNet = "BetaNet"
    SandNet = "SandNet"


class APIProvider:
    """abstract class to provide interface for API providers"""

    algod_hosts: dict[Network, str] = {}
    indexer_hosts: dict[Network, str] = {}

    def __init__(self, network: Network):
        self.network = network

    def algod(self, token: str = "") -> AlgodClient:
        """return an algod client based on the provider used and network it was initialized with"""
        if self.network not in self.algod_hosts:
            raise Exception(f"Unrecognized network: {self.network}")
        return AlgodClient(token, self.algod_hosts[self.network])

    def indexer(self, token: str = "") -> IndexerClient:
        """return an indexer client based on the provider used and network it was initialized with"""
        if self.network not in self.indexer_hosts:
            raise Exception(f"Unrecognized network: {self.network}")
        return IndexerClient(token, self.indexer_hosts[self.network])


class AlgoNode(APIProvider):
    algod_hosts = {
        Network.MainNet: "https://mainnet-api.algonode.cloud",
        Network.TestNet: "https://testnet-api.algonode.cloud",
        Network.BetaNet: "https://betanet-api.algonode.cloud",
    }

    indexer_hosts = {
        Network.MainNet: "https://mainnet-idx.algonode.cloud",
        Network.TestNet: "https://testnet-idx.algonode.cloud",
        Network.BetaNet: "https://betanet-idx.algonode.cloud",
    }


class AlgoExplorer(APIProvider):
    algod_hosts = {
        Network.MainNet: "https://node.algoexplorerapi.io",
        Network.TestNet: "https://node.testnet.algoexplorerapi.io",
        Network.BetaNet: "https://node.betanet.algoexplorerapi.io",
    }

    indexer_hosts = {
        Network.MainNet: "https://algoindexer.algoexplorerapi.io",
        Network.TestNet: "https://algoindexer.testnet.algoexplorerapi.io",
        Network.BetaNet: "https://algoindexer.betanet.algoexplorerapi.io",
    }


class PureStake(APIProvider):
    algod_hosts = {
        Network.MainNet: "https://mainnet-algorand.api.purestake.io/ps1",
        Network.TestNet: "https://testnet-algorand.api.purestake.io/ps1",
        Network.BetaNet: "https://betanet-algorand.api.purestake.io/ps1",
    }

    indexer_hosts = {
        Network.MainNet: "https://mainnet-algorand.api.purestake.io/idx2",
        Network.TestNet: "https://testnet-algorand.api.purestake.io/idx2",
        Network.BetaNet: "https://betanet-algorand.api.purestake.io/idx2",
    }

    token_header = "X-API-Key"

    # Purestake requires a different header, so we override the
    # existing methods but re-use them to generate the client
    def algod(self, token: str = "") -> AlgodClient:
        algod_client = super().algod()
        algod_client.headers = {self.token_header: token}

    def indexer(self, token: str = "") -> IndexerClient:
        indexer_client = super().algod()
        indexer_client.headers = {self.token_header: token}


class Sandbox(APIProvider):
    default_host = "http://localhost"
    default_algod_port: int = 4001
    default_indexer_port: int = 8980
    default_token: str = "a" * 64

    # purposely doesn't check which network because it may
    # be set up to use mainnet/testnet
    def algod(self, token: str = default_token) -> AlgodClient:
        address = f"{self.default_host}:{self.default_algod_port}"
        return AlgodClient(token, address)

    def indexer(self, token: str = default_token) -> IndexerClient:
        address = f"{self.default_host}:{self.default_indexer_port}"
        return IndexerClient(token, address)
