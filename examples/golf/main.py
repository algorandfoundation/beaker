import base64
from typing import Final
from algosdk import *
from pyteal import *
from beaker import *
from beaker.lib.math import max


@Subroutine(TealType.uint64)
def div_round(a, b) -> Expr:
    quo = a / b
    mod = a % b
    return If(mod > (b / Int(2)), quo + Int(1), quo)


class NumberOrder(Application):
    declared_count: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="wouldnt you like to know",
    )

    _box_name = "BoxA"
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
                If(self.declared_count == Int(0))
                .Then(Int(0))
                .Else(
                    self.binary_search(
                        val.get(),
                        array_contents.value(),
                        Int(0),
                        self.declared_count - Int(1),
                    )
                )
                * Int(8),
            ),
            self.declared_count.increment(),
            App.box_put(
                self.BoxName,
                # Take the bytes that would fit in the box
                self.insert_element(
                    array_contents.value(),
                    val.encode(),
                    idx.load(),
                ),
            ),
            Log(Itob(Global.opcode_budget())),
            # self.declared_count.increment(),
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
            Comment("in bin"),
            If(start > end, Return(start)),
            Comment("start<=end"),
            If(
                start == end,
                Return(
                    start + If(self.lookup_element(arr, start) > val, Int(0), Int(1))
                ),
            ),
            Comment("start!=end"),
            (mid := ScratchVar()).store((start + end) / Int(2)),
            (midval := ScratchVar()).store(self.lookup_element(arr, mid.load())),
            Comment("gotvals"),
            If(midval.load() < val)
            .Then(
                Comment("midval<val"),
                self.binary_search(val, arr, mid.load() + Int(1), end),
            )
            .ElseIf(midval.load() > val)
            .Then(
                Comment("midval>val"),
                self.binary_search(val, arr, start, max(Int(1), mid.load()) - Int(1)),
            )
            .Else(Comment("midval=val"), mid.load()),
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
            self.declared_count.set(Int(0)),
        )


def binary_search(arr, val, start, end):
    if start > end:
        return start

    if start == end:
        if arr[start] > val:
            return start
        return start + 1

    mid = (start + end) // 2

    if arr[mid] < val:
        return binary_search(arr, val, mid + 1, end)
    elif arr[mid] > val:
        return binary_search(arr, val, start, mid - 1)
    else:
        return mid


if __name__ == "__main__":
    # arr = []
    # for x in [37, 23, 0, 31, 22, 17, 12, 72, 31, 46, 100, 88, 54]:
    #    j = binary_search(arr, x, 0, len(arr) - 1)
    #    arr = arr[:j] + [x] + arr[j:]
    # print(arr)

    accts = sandbox.get_accounts()
    acct = accts.pop()
    acct2 = accts.pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), NumberOrder(version=8), signer=acct.signer
    )
    NumberOrder().dump("./artifacts")
    app_client.create()
    app_client.fund(100 * consts.algo)
    print(f"AppID: {app_client.app_id}  AppAddr: {app_client.app_addr}")

    boxes = [[app_client.app_id, "BoxA"]] * 4
    result = app_client.call(
        NumberOrder.box_create_test,
        boxes=boxes,
    )

    def decode_int(b: str) -> int:
        return int.from_bytes(base64.b64decode(b), "big")

    def decode_budget(tx_info) -> int:
        return decode_int(tx_info["logs"][0])

    def add_number(num: int) -> int:
        result = app_client.call(
            NumberOrder.add_int,
            val=num,
            boxes=boxes,
        )
        print([decode_int(v) for v in result.tx_info["logs"][:-1]])
        print(result.return_value)
        return decode_budget(result.tx_info)

    def get_box() -> list[int]:
        box_contents = app_client.client.application_box_by_name(
            app_client.app_id, b"BoxA"
        )

        vals = []
        print(box_contents["value"])
        data = base64.b64decode(box_contents["value"])
        for idx in range(len(data) // 8):
            vals.append(int.from_bytes(data[idx * 8 : (idx + 1) * 8], "big"))

        return vals

    import random

    nums = list(range(512))
    random.shuffle(nums)
    budgets = []
    for idx, n in enumerate(nums):
        print(f"Iteration {idx}: {n}")
        budgets.append(add_number(n))

    print(budgets)
    box = get_box()
    print(box)
    mx = 0
    for x in box:
        print(x)
        assert mx <= x
        mx = x
