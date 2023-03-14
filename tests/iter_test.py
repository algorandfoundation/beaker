import pyteal as pt

from beaker.lib.iter import Iterate

from tests.helpers import UnitTestingApp, assert_output


def test_iterate() -> None:
    ut = UnitTestingApp(
        pt.Seq(
            (buff := pt.ScratchVar()).store(pt.Bytes("")),
            Iterate(buff.store(pt.Concat(buff.load(), pt.Bytes("a"))), pt.Int(10)),
            buff.load(),
        )
    )

    output = [list(b"a" * 10)]
    assert_output(ut, [], output)


def test_iterate_default_stack_var_is_unique() -> None:
    inner_loop = 2
    outer_loop = 3
    ut = UnitTestingApp(
        pt.Seq(
            (buff := pt.ScratchVar()).store(pt.Bytes("")),
            Iterate(
                Iterate(
                    buff.store(pt.Concat(buff.load(), pt.Bytes("a"))),
                    pt.Int(inner_loop),
                ),
                pt.Int(outer_loop),
            ),
            buff.load(),
        )
    )

    output = [list(b"a" * inner_loop * outer_loop)]
    assert_output(ut, [], output)


def test_iterate_with_closure() -> None:
    i = pt.ScratchVar()
    buff = pt.ScratchVar()

    @pt.Subroutine(pt.TealType.none)
    def concat_thing() -> pt.Expr:
        return buff.store(pt.Concat(buff.load(), pt.Itob(i.load())))

    ut = UnitTestingApp(
        pt.Seq(
            buff.store(pt.Bytes("")),
            Iterate(concat_thing(), pt.Int(10), i),
            buff.load(),
        )
    )

    output = [list(b"".join([x.to_bytes(8, "big") for x in range(10)]))]

    assert_output(ut, [], output)
