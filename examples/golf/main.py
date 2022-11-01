import base64
from typing import Final
from algosdk import *
from pyteal import *
from beaker import *


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
            # Get the current array
            array_contents := App.box_get(self.BoxName),
            # figure out the correct index
            (i := ScratchVar()).store(Int(0)),
            While(i.load() < self.declared_count).Do(
                If(
                    val.get()
                    <= ExtractUint64(array_contents.value(), i.load() * Int(8)),
                    Break(),
                    i.store(i.load() + Int(1)),
                )
            ),
            self.declared_count.increment(),
            # Write the new array with the contents
            App.box_put(
                self.BoxName,
                # Take the bytes that would fit in the box
                self.insert_element(
                    array_contents.value(), val.encode(), i.load() * Int(8)
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

    def get_idx(last: Expr):
        pass

    def insert_element(self, buff: Expr, new_val: Expr, pos: Expr):
        return Concat(
            Extract(buff, Int(0), pos),
            new_val,
            # extract from pos -> max len of box leaving off
            Extract(buff, pos, self.BoxSize - pos - Int(8)),
        )

    @external
    def box_create_test(self):
        return Seq(
            Assert(App.box_create(self.BoxName, self.BoxSize)),
            self.declared_count.set(Int(0)),
        )


if __name__ == "__main__":
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

    def decode_budget(tx_info) -> int:
        return int.from_bytes(base64.b64decode(tx_info["logs"][0]), "big")

    def add_number(num: int) -> int:
        result = app_client.call(
            NumberOrder.add_int,
            val=num,
            boxes=boxes,
        )
        print(result.return_value)
        return decode_budget(result.tx_info)

    def get_box() -> list[int]:
        box_contents = app_client.client.application_box_by_name(
            app_client.app_id, b"BoxA"
        )

        vals = []
        data = base64.b64decode(box_contents["value"])
        for idx in range(len(data) // 8):
            vals.append(int.from_bytes(data[idx * 8 : (idx + 1) * 8], "big"))

        return vals

    import random

    nums = list(range(40))
    random.shuffle(nums)
    budgets = []
    for idx, n in enumerate(nums):
        print(f"Iteration {idx}: {n}")
        budgets.append(add_number(n))

    print(budgets)
    print(get_box())
