from pyteal import ScratchSlot, Itob, Log, Int, Seq

from tests.helpers import logged_int, assert_output

from .inline_asm import InlineAssembly


def test_inline_assembly():
    get_uint8 = """
extract 7 1
"""
    s = ScratchSlot()
    expr = Seq(InlineAssembly(get_uint8, Itob(Int(255))), s.store(), Log(s.load()))

    expected = [logged_int(255)[-2:]]
    assert_output(expr, expected)


# def test_inline_assembly_invalid():
#    get_uint8 = """
# extract a b
# """
#    s = ScratchSlot()
#    expr = Seq(InlineAssembly(get_uint8, Itob(Int(255))), s.store(), Log(s.load()))
#
#    expected = [
#        INVALID_SYNTAX
#    ]  # TODO: in the next version, this will be "unable to parse"
#    assert_fail(expr, expected)
