import pyteal as pt

from beaker.testing.helpers import UnitTestingApp, assert_abi_output
from beaker.lib.inline import InlineAssembly


def test_inline_assembly():

    get_uint8 = """
extract 7 1
"""

    s = pt.ScratchSlot()

    ut = UnitTestingApp(
        InlineAssembly(get_uint8, pt.Itob(pt.Int(255)), type=pt.TealType.bytes),
    )

    expected = [255]
    assert_abi_output(ut, [], [expected])
