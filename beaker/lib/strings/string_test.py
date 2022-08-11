import pytest
import pyteal as pt
import beaker as bkr

from beaker.testing.helpers import (
    UnitTestingApp,
    assert_abi_output,
    LOGIC_EVAL_ERROR,
    returned_int,
)

from beaker.lib.strings import atoi, encode_uvarint, head, itoa, prefix, suffix, tail


def test_atoi():
    ut = UnitTestingApp(pt.Itob(atoi(pt.Bytes("123"))))
    output = [returned_int(int(123))]
    assert_abi_output(ut, [], output)


def test_atoi_invalid():
    ut = UnitTestingApp(pt.Itob(atoi(pt.Bytes("abc"))))
    output = [returned_int(int(123))]
    with pytest.raises(bkr.client.LogicException):
        assert_abi_output(ut, [], output)


def test_itoa():
    ut = UnitTestingApp(itoa(pt.Int(123)))
    output = [list(b"123")]
    assert_abi_output(ut, [], output)


def test_head():
    ut = UnitTestingApp(head(pt.Bytes("deadbeef")))
    output = [list(b"d")]
    assert_abi_output(ut, [], output)


def test_head_empty():
    ut = UnitTestingApp(tail(pt.Bytes("")))

    with pytest.raises(bkr.client.LogicException):
        assert_abi_output(ut, [], [LOGIC_EVAL_ERROR])


def test_tail():
    ut = UnitTestingApp(tail(pt.Bytes("deadbeef")))
    output = [list(b"eadbeef")]
    assert_abi_output(ut, [], output)


def test_tail_empty():
    ut = UnitTestingApp(tail(pt.Bytes("")))
    with pytest.raises(bkr.client.LogicException):
        assert_abi_output(ut, [], [LOGIC_EVAL_ERROR])


def test_suffix():
    ut = UnitTestingApp(suffix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"ef")]
    assert_abi_output(ut, [], output)


def test_suffix_past_length():
    ut = UnitTestingApp(suffix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(bkr.client.LogicException):
        assert_abi_output(ut, [], [LOGIC_EVAL_ERROR])


def test_prefix():
    ut = UnitTestingApp(prefix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"de")]
    assert_abi_output(ut, [], output)


def test_prefix_past_length():
    ut = UnitTestingApp(prefix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(bkr.client.LogicException):
        assert_abi_output(ut, [], [LOGIC_EVAL_ERROR])


def test_encode_uvarint():
    ut = UnitTestingApp(encode_uvarint(pt.Int(500), pt.Bytes("")))
    output = [[244, 3]]
    assert_abi_output(ut, [], output)
