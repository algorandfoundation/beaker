from pyteal import Expr, For, Int, ScratchVar

__all__ = [
    "Iterate",
]


def Iterate(sub: Expr, n: Int, i: ScratchVar | None = None) -> Expr:
    """Iterate provides a convenience method for calling a method n times

    Args:
        sub: A PyTEAL Expr to call, should not return anything
        n: The number of times to call the expression
        i: (Optional) A ScratchVar to use for iteration, passed if the caller wants to access the iterator

    Returns:
        A Subroutine expression to be passed directly into an Expr tree
    """

    i = i or ScratchVar()
    init = i.store(Int(0))
    cond = i.load() < n
    step = i.store(i.load() + Int(1))
    return For(init, cond, step).Do(sub)
