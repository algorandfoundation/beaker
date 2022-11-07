import pyteal as pt
from ._list import List


def test_list():
    l = List(pt.abi.Uint64, 100)

    assert l._elements == 100
    assert l._element_size == 8
    assert l._box_size == 8 * 100
    assert l.value_type == pt.abi.Uint64TypeSpec()
