import pyteal as pt
import pytest
from algokit_utils import LogicError

from beaker.lib.strings import Atoi, EncodeUVarInt, Head, Itoa, Prefix, Suffix, Tail

from tests.helpers import (
    UnitTestingApp,
    assert_output,
    returned_int_as_bytes,
)


def test_atoi() -> None:
    ut = UnitTestingApp(pt.Itob(Atoi(pt.Bytes("123"))))
    output = [returned_int_as_bytes(int(123))]
    assert_output(ut, [], output)


def test_atoi_invalid() -> None:
    ut = UnitTestingApp(pt.Itob(Atoi(pt.Bytes("abc"))))
    output = [returned_int_as_bytes(int(123))]
    with pytest.raises(LogicError):
        assert_output(ut, [], output)


def test_itoa() -> None:
    ut = UnitTestingApp(Itoa(pt.Int(123)))
    output = [list(b"123")]
    assert_output(ut, [], output)


def test_head() -> None:
    ut = UnitTestingApp(Head(pt.Bytes("deadbeef")))
    output = [list(b"d")]
    assert_output(ut, [], output)


def test_head_empty() -> None:
    ut = UnitTestingApp(Tail(pt.Bytes("")))

    with pytest.raises(LogicError):
        assert_output(ut, [], [None])


def test_tail() -> None:
    ut = UnitTestingApp(Tail(pt.Bytes("deadbeef")))
    output = [list(b"eadbeef")]
    assert_output(ut, [], output)


def test_tail_empty() -> None:
    ut = UnitTestingApp(Tail(pt.Bytes("")))
    with pytest.raises(LogicError):
        assert_output(ut, [], [None])


def test_suffix() -> None:
    ut = UnitTestingApp(Suffix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"ef")]
    assert_output(ut, [], output)


def test_suffix_past_length() -> None:
    ut = UnitTestingApp(Suffix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(LogicError):
        assert_output(ut, [], [None])


def test_prefix() -> None:
    ut = UnitTestingApp(Prefix(pt.Bytes("deadbeef"), pt.Int(2)))
    output = [list(b"de")]
    assert_output(ut, [], output)


def test_prefix_past_length() -> None:
    ut = UnitTestingApp(Prefix(pt.Bytes("deadbeef"), pt.Int(9)))
    with pytest.raises(LogicError):
        assert_output(ut, [], [None])


def test_encode_uvarint() -> None:
    ut = UnitTestingApp(EncodeUVarInt(pt.Int(500)))
    output = [[244, 3]]
    assert_output(ut, [], output)
