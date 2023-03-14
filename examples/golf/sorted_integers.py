import pyteal as pt

import beaker
from beaker.lib.math import Max


class SortedIntegersState:
    elements = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
        descr="The number of elements in the array",
    )


BOX_NAME = "sorted_ints"
BOX_SIZE = 1024 * 4
MAX_INTS = BOX_SIZE // 8

BOX_NAME_EXPR = pt.Bytes(BOX_NAME)
BOX_SIZE_EXPR = pt.Int(BOX_SIZE)
MAX_INTS_EXPR = pt.Int(MAX_INTS)

app = beaker.Application(
    "SortedIntegers",
    build_options=beaker.BuildOptions(avm_version=8),
    state=SortedIntegersState(),
)


@app.external
def add_int(
    val: pt.abi.Uint64, *, output: pt.abi.DynamicArray[pt.abi.Uint64]
) -> pt.Expr:
    return pt.Seq(
        array_contents := pt.App.box_get(BOX_NAME_EXPR),
        pt.Assert(pt.Or(pt.Int(0), pt.Int(1))),
        # figure out the correct index
        # Write the new array with the contents
        (idx := pt.ScratchVar()).store(
            pt.If(
                app.state.elements == pt.Int(0),
                pt.Int(0),
                binary_search(
                    val.get(),
                    array_contents.value(),
                    pt.Int(0),
                    app.state.elements - pt.Int(1),
                )
                * pt.Int(8),
            )
        ),
        pt.App.box_put(
            BOX_NAME_EXPR,
            # Take the bytes that would fit in the box
            insert_element(
                array_contents.value(),
                val.encode(),
                idx.load(),
            ),
        ),
        app.state.elements.increment(),
        pt.Log(pt.Itob(pt.Global.opcode_budget())),
        output.decode(
            # Prepend the bytes with the number of elements as a uint16,
            # according to ABI spec
            pt.Concat(
                pt.Suffix(pt.Itob(pt.Int(10)), pt.Int(6)),
                pt.App.box_extract(BOX_NAME_EXPR, pt.Int(0), pt.Int(8) * pt.Int(10)),
            )
        ),
    )


@pt.Subroutine(pt.TealType.uint64)
def binary_search(val: pt.Expr, arr: pt.Expr, start: pt.Expr, end: pt.Expr) -> pt.Expr:
    # Python equivalent:
    # def binary_search(arr, val, start, end):
    #     if start > end:
    #         return start
    #
    #     if start == end:
    #         if arr[start] > val:
    #             return start
    #         return start + 1
    #
    #     mid = (start + end) // 2
    #
    #     if arr[mid] < val:
    #         return binary_search(arr, val, mid + 1, end)
    #     elif arr[mid] > val:
    #         return binary_search(arr, val, start, mid - 1)
    #     else:
    #         return mid

    return pt.Seq(
        pt.If(start > end, pt.Return(start)),
        pt.If(
            start == end,
            pt.Return(
                start + pt.If(lookup_element(arr, start) > val, pt.Int(0), pt.Int(1))
            ),
        ),
        (mididx := pt.ScratchVar()).store((start + end) / pt.Int(2)),
        (midval := pt.ScratchVar()).store(lookup_element(arr, mididx.load())),
        pt.If(midval.load() < val)
        .Then(
            binary_search(val, arr, mididx.load() + pt.Int(1), end),
        )
        .ElseIf(midval.load() > val)
        .Then(
            binary_search(val, arr, start, Max(pt.Int(1), mididx.load()) - pt.Int(1)),
        )
        .Else(mididx.load()),
    )


def lookup_element(buff: pt.Expr, idx: pt.Expr) -> pt.Expr:
    return pt.ExtractUint64(buff, idx * pt.Int(8))


def insert_element(buff: pt.Expr, new_val: pt.Expr, pos: pt.Expr) -> pt.Expr:
    return pt.Concat(
        pt.Extract(buff, pt.Int(0), pos),
        new_val,
        # extract from pos -> max len of box leaving off
        pt.Extract(buff, pos, (BOX_SIZE_EXPR - pos) - pt.Int(8)),
    )


@app.external
def box_create_test() -> pt.Expr:
    return pt.Seq(
        pt.Assert(pt.App.box_create(BOX_NAME_EXPR, BOX_SIZE_EXPR)),
        app.state.elements.set(pt.Int(0)),
    )
