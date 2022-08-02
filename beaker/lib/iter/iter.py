from typing import List

from pyteal import BinaryExpr, Expr, For, Int, Op, ScratchVar, Seq, Subroutine, TealType


def accumulate(vals: List[Expr], op: Op) -> Expr:
    """accumulate provides a convenient way to efficiently combine elements in a list.

    Pairs elements of the vals list recursively to save on ops and reduce the need for intermediate scratch var storing/loading

    Typical Usage Example:
        accumulate([Int(1), Int(2), Int(3), Int(4)], Op.Add) # comes out to (1+2)+(3+4) == 10

    Args:
        vals: A List of Expr objects to evaluate, these should evaluate to a Bytes or Int
        op: A teal operation to perform on the list

    Returns:
        A single expression representing the accumulated value after applying the op for all elements

    """
    ops: List[Expr] = []
    for n in range(0, len(vals) - 1, 2):
        ops.append(
            BinaryExpr(op, TealType.uint64, TealType.uint64, vals[n], vals[n + 1])
        )

    # If its an odd number, we cant match it, just add the last one
    if len(vals) % 2 == 1:
        ops.append(vals[-1])

    if len(ops) > 1:
        return accumulate(ops, op)

    return Seq(ops)


def iterate(sub: Expr, n: Int, i: ScratchVar = ScratchVar()) -> Expr:
    """Iterate provides a convenience method for calling a method n times

    Args:
        sub: A PyTEAL Expr to call, should not return anything
        n: The number of times to call the expression
        i: (Optional) A ScratchVar to use for iteration, passed if the caller wants to access the iterator

    Returns:
        A Subroutine expression to be passed directly into an Expr tree
    """

    @Subroutine(TealType.none)
    def _impl() -> Expr:
        init = i.store(Int(0))
        cond = i.load() < n
        iter = i.store(i.load() + Int(1))
        return For(init, cond, iter).Do(sub)

    return _impl()
