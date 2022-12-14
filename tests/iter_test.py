import pyteal as pt
from beaker.testing.unit_testing_helpers import UnitTestingApp, assert_output

from beaker.lib.iter import iterate


def test_iterate():
    ut = UnitTestingApp(
        pt.Seq(
            (buff := pt.ScratchVar()).store(pt.Bytes("")),
            iterate(buff.store(pt.Concat(buff.load(), pt.Bytes("a"))), pt.Int(10)),
            buff.load(),
        )
    )

    output = [list(b"a" * 10)]
    assert_output(ut, [], output)


def test_iterate_with_closure():
    i = pt.ScratchVar()
    buff = pt.ScratchVar()

    @pt.Subroutine(pt.TealType.none)
    def concat_thing():
        return buff.store(pt.Concat(buff.load(), pt.Itob(i.load())))

    ut = UnitTestingApp(
        pt.Seq(
            buff.store(pt.Bytes("")),
            iterate(concat_thing(), pt.Int(10), i),
            buff.load(),
        )
    )

    output = [list(b"".join([x.to_bytes(8, "big") for x in range(10)]))]

    assert_output(ut, [], output)
