import beaker

from examples.merkle_tree.application import app
from examples.merkle_tree.merkle import TREE_HEIGHT
from examples.merkle_tree.offchain_merkle import MerkleTree


def main() -> None:
    accts = beaker.sandbox.get_accounts()
    algod = beaker.sandbox.get_algod_client()

    app_client = beaker.client.ApplicationClient(algod, app, signer=accts[0].signer)
    app_client.create()
    print(app_client.get_global_state())

    mt = MerkleTree(TREE_HEIGHT)

    for i in range(2**TREE_HEIGHT):
        data = f"record{i}"
        path = mt.append(data)
        result = app_client.call("append_leaf", data=data.encode(), path=path[1:])
        print(result.tx_info["confirmed-round"])

    for i in range(2**TREE_HEIGHT):
        data = f"record{i}"
        path = mt.verify(data)
        result = app_client.call("verify_leaf", data=data.encode(), path=path[1:])
        print(result.tx_info["confirmed-round"])

    for i in range(2**TREE_HEIGHT):
        old_data = f"record{i}"
        new_data = f"record{i}{i}"
        path = mt.update(old_data, new_data)
        result = app_client.call(
            "update_leaf",
            old_data=old_data.encode(),
            new_data=new_data.encode(),
            path=path[1:-1],
        )
        print(result.tx_info["confirmed-round"])

    for i in range(2**TREE_HEIGHT):
        data = f"record{i}{i}"
        path = mt.verify(data)
        result = app_client.call("verify_leaf", data=data.encode(), path=path[1:])
        print(result.tx_info["confirmed-round"])


if __name__ == "__main__":
    main()
