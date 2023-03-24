import base64
import random

from beaker import client, consts, sandbox

from examples.golf import sorted_integers


#
# Util funcs
#
def decode_int(b: str) -> int:
    return int.from_bytes(base64.b64decode(b), "big")


def decode_budget(tx_info: dict) -> int:
    return decode_int(tx_info["logs"][0])


def get_box(app_client: client.ApplicationClient, name: bytes) -> list[int]:
    box_contents = app_client.client.application_box_by_name(app_client.app_id, name)
    assert isinstance(box_contents, dict)

    vals = []
    data = base64.b64decode(box_contents["value"])
    for idx in range(len(data) // 8):
        vals.append(int.from_bytes(data[idx * 8 : (idx + 1) * 8], "big"))

    return vals


def main() -> None:
    acct = sandbox.get_accounts().pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), sorted_integers.app, signer=acct.signer
    )

    # Create && fund app acct
    app_client.create()
    app_client.fund(100 * consts.algo)
    print(f"AppID: {app_client.app_id}  AppAddr: {app_client.app_addr}")

    # Create 4 box refs since we need to touch 4k
    boxes = [(app_client.app_id, sorted_integers.BOX_NAME)] * 4

    # Make App Create box
    app_client.call(
        sorted_integers.box_create_test,
        boxes=boxes,
    )

    # Shuffle 0-511
    nums = list(range(512))
    random.shuffle(nums)
    budgets = []
    for idx, n in enumerate(nums):
        if idx % 32 == 0:
            print(f"Iteration {idx}: {n}")

        result = app_client.call(
            sorted_integers.add_int,
            val=n,
            boxes=boxes,
        )

        budgets.append(decode_budget(result.tx_info))

    print(f"Budget left after each insert: {budgets}")

    # Get contents of box
    box = get_box(app_client, sorted_integers.BOX_NAME.encode())
    # Make sure its sorted
    assert box == sorted(box)


if __name__ == "__main__":
    main()
