from beaker.client.api_providers import (
    Network,
    Sandbox,
    AlgoNode,
    AlgoExplorer,
    PureStake,
)


def test_sandbox():
    sb = Sandbox(Network.SandNet)
    sb.algod().suggested_params()
    # sandbox indexer off
    # sb.indexer().health()


def test_algonode():
    for network in Network:
        if network == Network.SandNet:
            continue
        print(f"trying {network}")
        an = AlgoNode(network)
        an.algod().suggested_params()
        an.indexer().health()


def test_algoexplorer():
    for network in Network:
        if network == Network.SandNet:
            continue

        print(f"trying {network}")
        ae = AlgoExplorer(network)
        ae.algod().suggested_params()
        ae.indexer().health()


def test_purestake():
    return

    api_key = "TODO"
    for network in Network:
        if network == Network.SandNet:
            continue

        print(f"trying {network}")
        ae = PureStake(network)
        ae.algod(api_key).suggested_params()
        ae.indexer(api_key).health()
