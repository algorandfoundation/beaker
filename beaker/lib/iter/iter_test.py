from pyteal import (
    Bytes,
    Int,
    Itob,
    Log,
    ScratchVar,
    Subroutine,
    SubroutineCall,
    TealType,
)

from beaker.testing.helpers import assert_output, logged_bytes, logged_int

from .iter import iterate


def test_iterate():
    expr = iterate(Log(Bytes("a")), Int(10))
    assert type(expr) is SubroutineCall

    output = [logged_bytes("a")] * 10
    assert_output(expr, output)


def test_iterate_with_closure():
    i = ScratchVar()

    @Subroutine(TealType.none)
    def logthing():
        return Log(Itob(i.load()))

    expr = iterate(logthing(), Int(10), i)
    assert type(expr) is SubroutineCall

    output = [logged_int(x) for x in range(10)]
    assert_output(expr, output)
