import base64
import random
from typing import Final
from algosdk import *
from pyteal import *
from beaker import *
from beaker.lib.math import max


class NumberOrder(Application):
    elements: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="The number of elements in the array",
    )

    _box_name = "sorted_ints"
    _box_size = 1024 * 4
    _max_ints = _box_size // 8

    BoxName = Bytes(_box_name)
    BoxSize = Int(_box_size)
    MaxInts = Int(_max_ints)

    @external
    def add_int(self, val: abi.Uint64, *, output: abi.DynamicArray[abi.Uint64]):
        return Seq(
            array_contents := App.box_get(self.BoxName),
            # figure out the correct index
            # Write the new array with the contents
            (idx := ScratchVar()).store(
                If(
                    self.elements == Int(0),
                    Int(0),
                    self.binary_search(
                        val.get(),
                        array_contents.value(),
                        Int(0),
                        self.elements - Int(1),
                    )
                    * Int(8),
                )
            ),
            App.box_put(
                self.BoxName,
                # Take the bytes that would fit in the box
                self.insert_element(
                    array_contents.value(),
                    val.encode(),
                    idx.load(),
                ),
            ),
            self.elements.increment(),
            Log(Itob(Global.opcode_budget())),
            output.decode(
                # Prepend the bytes with the number of elements as a uint16, according to ABI spec
                Concat(
                    Suffix(Itob(Int(10)), Int(6)),
                    App.box_extract(self.BoxName, Int(0), Int(8) * Int(10)),
                )
            ),
        )

    @internal(TealType.uint64)
    def binary_search(self, val: Expr, arr: Expr, start: Expr, end: Expr) -> Expr:
        return Seq(
            If(start > end, Return(start)),
            If(
                start == end,
                Return(
                    start + If(self.lookup_element(arr, start) > val, Int(0), Int(1))
                ),
            ),
            (mididx := ScratchVar()).store((start + end) / Int(2)),
            (midval := ScratchVar()).store(self.lookup_element(arr, mididx.load())),
            If(midval.load() < val)
            .Then(
                self.binary_search(val, arr, mididx.load() + Int(1), end),
            )
            .ElseIf(midval.load() > val)
            .Then(
                self.binary_search(
                    val, arr, start, max(Int(1), mididx.load()) - Int(1)
                ),
            )
            .Else(mididx.load()),
        )

    def lookup_element(self, buff: Expr, idx: Expr):
        return ExtractUint64(buff, idx * Int(8))

    def insert_element(self, buff: Expr, new_val: Expr, pos: Expr):
        return Concat(
            Extract(buff, Int(0), pos),
            new_val,
            # extract from pos -> max len of box leaving off
            Extract(buff, pos, (self.BoxSize - pos) - Int(8)),
        )

    @external
    def box_create_test(self):
        return Seq(
            Assert(App.box_create(self.BoxName, self.BoxSize)),
            self.elements.set(Int(0)),
        )


#
# Util funcs
#
def decode_int(b: str) -> int:
    return int.from_bytes(base64.b64decode(b), "big")


def decode_budget(tx_info) -> int:
    return decode_int(tx_info["logs"][0])


def get_box(app_id: int, name: bytes, client: v2client.algod.AlgodClient) -> list[int]:
    box_contents = client.application_box_by_name(app_id, name)

    vals = []
    data = base64.b64decode(box_contents["value"])
    for idx in range(len(data) // 8):
        vals.append(int.from_bytes(data[idx * 8 : (idx + 1) * 8], "big"))

    return vals


def demo():
    acct = sandbox.get_accounts().pop()

    app = NumberOrder(version=8)
    app.dump("./artifacts")

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), app, signer=acct.signer
    )

    # Create && fund app acct
    app_client.create()
    app_client.fund(100 * consts.algo)
    print(f"AppID: {app_client.app_id}  AppAddr: {app_client.app_addr}")

    # Create 4 box refs since we need to touch 4k
    boxes = [[app_client.app_id, app._box_name]] * 4

    # Make App Create box
    result = app_client.call(
        NumberOrder.box_create_test,
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
            NumberOrder.add_int,
            val=n,
            boxes=boxes,
        )

        budgets.append(decode_budget(result.tx_info))

    print(budgets)

    # Get contents of box
    print(box := get_box(app_client.app_id, app._box_name.encode(), app_client.client))
    # Make sure its sorted
    mx = 0
    for x in box:
        assert mx <= x
        mx = x


if __name__ == "__main__":
    demo()
