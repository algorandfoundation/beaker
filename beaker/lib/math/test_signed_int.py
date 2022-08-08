from pyteal import Int, Itob, Log, Seq

from tests.helpers import assert_output, logged_int

from .signed_int import SignedInt


def test_signed_sub():
    num = 100
    expr = Seq(
        Log(Itob(SignedInt(num) - SignedInt(num + 1))),
        Log(Itob(SignedInt(num) + SignedInt(num + 1))),
    )

    output = ["ff" * 8, logged_int(num + num + 1)]
    assert_output(expr, output)


def test_signed_sub_add():
    num = 100
    expr = Seq(
        Log(Itob(SignedInt.add(SignedInt(num) - SignedInt(num + 5), Int(num + 5))))
    )
    output = [logged_int(num)]
    assert_output(expr, output)


def test_signed_static():
    expr = Log(Itob(SignedInt.subtract(Int(10), Int(11))))
    output = ["ff" * 8]
    assert_output(expr, output)
