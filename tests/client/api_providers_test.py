import pytest

from beaker.client.api_providers import (
    AlgoExplorer,
    AlgoNode,
    Network,
    PureStake,
    Sandbox,
)

pytestmark = pytest.mark.network


def test_sandbox() -> None:
    sb = Sandbox(Network.SandNet)
    sb.algod().suggested_params()
    # sandbox indexer off
    # sb.indexer().health()


def test_algonode() -> None:
    for network in Network:
        if network == Network.SandNet:
            continue
        print(f"trying {network}")
        an = AlgoNode(network)
        an.algod().suggested_params()
        an.indexer().health()


def test_algoexplorer() -> None:
    for network in Network:
        if network == Network.SandNet:
            continue

        print(f"trying {network}")
        ae = AlgoExplorer(network)
        # ae.algod().suggested_params()
        ae.indexer().health()


def test_purestake() -> None:
    return

    api_key = "TODO"
    for network in Network:
        if network == Network.SandNet:
            continue

        print(f"trying {network}")
        ae = PureStake(network)
        ae.algod(api_key).suggested_params()
        ae.indexer(api_key).health()
