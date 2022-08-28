from pyteal import Expr, For, Int, ScratchVar, Subroutine, TealType


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
