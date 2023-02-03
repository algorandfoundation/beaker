import base64
import random
from typing import Final

from algosdk import v2client
from pyteal import (
    App,
    Or,
    Return,
    Subroutine,
    Log,
    abi,
    Extract,
    TealType,
    Int,
    Global,
    Concat,
    Bytes,
    ExtractUint64,
    Assert,
    ScratchVar,
    Suffix,
    Expr,
    Itob,
    If,
    Seq,
)


from beaker import Application, ApplicationStateValue, sandbox, client, consts
from beaker.application import CompilerOptions
from beaker.blueprints import unconditional_create_approval
from beaker.lib.math import Max


class SortedIntegersState:
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

sorted_ints_app = Application(
    "SortedIntegers",
    compiler_options=CompilerOptions(avm_version=8),
    state_class=SortedIntegersState,
).implement(unconditional_create_approval)


@sorted_ints_app.external
def add_int(val: abi.Uint64, *, output: abi.DynamicArray[abi.Uint64]):
    return Seq(
        array_contents := App.box_get(BoxName),
        Assert(Or(Int(0), Int(1))),
        # figure out the correct index
        # Write the new array with the contents
        (idx := ScratchVar()).store(
            If(
                SortedIntegersState.elements == Int(0),
                Int(0),
                binary_search(
                    val.get(),
                    array_contents.value(),
                    Int(0),
                    SortedIntegersState.elements - Int(1),
                )
                * Int(8),
            )
        ),
        App.box_put(
            BoxName,
            # Take the bytes that would fit in the box
            insert_element(
                array_contents.value(),
                val.encode(),
                idx.load(),
            ),
        ),
        SortedIntegersState.elements.increment(),
        Log(Itob(Global.opcode_budget())),
        output.decode(
            # Prepend the bytes with the number of elements as a uint16,
            # according to ABI spec
            Concat(
                Suffix(Itob(Int(10)), Int(6)),
                App.box_extract(BoxName, Int(0), Int(8) * Int(10)),
            )
        ),
    )


@Subroutine(TealType.uint64)
def binary_search(val: Expr, arr: Expr, start: Expr, end: Expr) -> Expr:
    return Seq(
        If(start > end, Return(start)),
        If(
            start == end,
            Return(start + If(lookup_element(arr, start) > val, Int(0), Int(1))),
        ),
        (mididx := ScratchVar()).store((start + end) / Int(2)),
        (midval := ScratchVar()).store(lookup_element(arr, mididx.load())),
        If(midval.load() < val)
        .Then(
            binary_search(val, arr, mididx.load() + Int(1), end),
        )
        .ElseIf(midval.load() > val)
        .Then(
            binary_search(val, arr, start, Max(Int(1), mididx.load()) - Int(1)),
        )
        .Else(mididx.load()),
    )


def lookup_element(buff: Expr, idx: Expr):
    return ExtractUint64(buff, idx * Int(8))


def insert_element(buff: Expr, new_val: Expr, pos: Expr):
    return Concat(
        Extract(buff, Int(0), pos),
        new_val,
        # extract from pos -> max len of box leaving off
        Extract(buff, pos, (BoxSize - pos) - Int(8)),
    )


@sorted_ints_app.external
def box_create_test():
    return Seq(
        Assert(App.box_create(BoxName, BoxSize)),
        SortedIntegersState.elements.set(Int(0)),
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

    app = sorted_ints_app

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), app, signer=acct.signer
    )

    # Create && fund app acct
    app_client.create()
    app_client.fund(100 * consts.algo)
    print(f"AppID: {app_client.app_id}  AppAddr: {app_client.app_addr}")

    # Create 4 box refs since we need to touch 4k
    boxes = [(app_client.app_id, _box_name)] * 4

    # Make App Create box
    result = app_client.call(
        box_create_test,
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
            add_int,
            val=n,
            boxes=boxes,
        )

        budgets.append(decode_budget(result.tx_info))

    print(f"Budget left after each insert: {budgets}")

    # Get contents of box
    box = get_box(app_client.app_id, _box_name.encode(), app_client.client)
    # Make sure its sorted
    assert box == sorted(box)


if __name__ == "__main__":
    demo()
