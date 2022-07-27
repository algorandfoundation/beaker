from pyteal import (
    Bytes,
    Int,
    Itob,
    Log,
    Op,
    ScratchVar,
    Subroutine,
    SubroutineCall,
    TealType,
)

from tests.helpers import assert_output, logged_bytes, logged_int

from .iter import accumulate, iterate


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


def test_accumulate():
    expr = Log(Itob(accumulate([Int(1) for _ in range(10)], Op.add)))
    output = [logged_int(10)]
    assert_output(expr, output)
