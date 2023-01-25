import pytest
import pyteal as pt
from hashmap import HashMap, itob, btoi


def test_hm_put_max():
    hm = HashMap(pt.abi.Uint64)

    for key in range(hm.max_slots):
        val = 123 + key
        hm.put(key, itob(val))
        got = btoi(hm.get(key))
        assert val == got

    hm.print_debug()


def test_hm_put_get():
    hm = HashMap(pt.abi.Uint64)

    val = 123
    hm.put(10, itob(val))
    got = btoi(hm.get(10))
    assert val == got

    hm.put(10, itob(val + 1))
    got = btoi(hm.get(10))
    assert val + 1 == got


def test_hm_delete():
    hm = HashMap(pt.abi.Uint64)

    val = 123
    hm.put(10, itob(val))
    got = btoi(hm.get(10))
    assert val == got

    hm.delete(10)

    with pytest.raises(KeyError):
        hm.get(10)
