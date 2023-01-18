import pytest
import pyteal as pt
import beaker as bkr

from beaker.testing import (
    UnitTestingApp,
    assert_output,
    returned_int_as_bytes,
)

from beaker.lib.strings import Atoi, EncodeUvariant, Head, Itoa, Prefix, Suffix, Tail


def test_atoi():
    ut = UnitTestingApp(pt.Itob(Atoi(pt.Bytes("123"))))
    output = [returned_int_as_bytes(int(123))]
    assert_output(ut, [], output)


def test_atoi_invalid():
    ut = UnitTestingApp(pt.Itob(Atoi(pt.Bytes("abc"))))
    output = [returned_int_as_bytes(int(123))]
    with pytest.raises(bkr.client.LogicException):
        assert_output(ut, [], output)


def test_itoa():
    ut = UnitTestingApp(Itoa(pt.Int(123)))
    output = [list(b"123")]
    assert_output(ut, [], output)


def test_head():
    ut = UnitTestingApp(Head(pt.Bytes("deadbeef")))
    output = [list(b"d")]
    assert_output(ut, [], output)


def test_head_empty():
    ut = UnitTestingApp(Tail(pt.Bytes("")))

    with pytest.raises(bkr.client.LogicException):
        assert_output(ut, [], [None])


def test_tail():
    ut = UnitTestingApp(Tail(pt.Bytes("deadbeef")))
    output = [list(b"eadbeef")]
    assert_output(ut, [], output)


def test_tail_empty():
    ut = UnitTestingApp(Tail(pt.Bytes("")))
    with pytest.raises(bkr.client.LogicException):
        assert_output(ut, [], [None])


def test_suffix():
    ut = UnitTestingApp(Suffix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"ef")]
    assert_output(ut, [], output)


def test_suffix_past_length():
    ut = UnitTestingApp(Suffix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(bkr.client.LogicException):
        assert_output(ut, [], [None])


def test_prefix():
    ut = UnitTestingApp(Prefix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"de")]
    assert_output(ut, [], output)


def test_prefix_past_length():
    ut = UnitTestingApp(Prefix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(bkr.client.LogicException):
        assert_output(ut, [], [None])


def test_encode_uvarint():
    ut = UnitTestingApp(EncodeUvariant(pt.Int(500)))
    output = [[244, 3]]
    assert_output(ut, [], output)
