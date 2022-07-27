from pyteal import Bytes, Int, Itob, Log

from tests.helpers import (
    LOGIC_EVAL_ERROR,
    assert_fail,
    assert_output,
    logged_bytes,
    logged_int,
)

from .string import atoi, encode_uvarint, head, itoa, prefix, suffix, tail


def test_atoi():
    expr = Log(Itob(atoi(Bytes("123"))))
    output = [logged_int(int(123))]
    assert_output(expr, output)


def test_atoi_invalid():
    expr = Log(Itob(atoi(Bytes("abc"))))
    assert_fail(expr, [LOGIC_EVAL_ERROR])


def test_itoa():
    expr = Log(itoa(Int(123)))
    output = [logged_bytes("123")]
    assert_output(expr, output)


def test_head():
    expr = Log(head(Bytes("deadbeef")))
    output = [logged_bytes("d")]
    assert_output(expr, output)


def test_head_empty():
    expr = Log(tail(Bytes("")))
    assert_fail(expr, [LOGIC_EVAL_ERROR])


def test_tail():
    expr = Log(tail(Bytes("deadbeef")))
    output = [logged_bytes("eadbeef")]
    assert_output(expr, output)


def test_tail_empty():
    expr = Log(tail(Bytes("")))
    assert_fail(expr, [LOGIC_EVAL_ERROR])


def test_suffix():
    expr = Log(suffix(Bytes("deadbeef"), Int(2)))
    output = [logged_bytes("ef")]
    assert_output(expr, output)


def test_suffix_past_length():
    expr = Log(suffix(Bytes("deadbeef"), Int(9)))
    assert_fail(expr, [LOGIC_EVAL_ERROR])


def test_prefix():
    expr = Log(prefix(Bytes("deadbeef"), Int(2)))
    output = [logged_bytes("de")]
    assert_output(expr, output)


def test_prefix_past_length():
    expr = Log(prefix(Bytes("deadbeef"), Int(9)))
    assert_fail(expr, [LOGIC_EVAL_ERROR])


def test_encode_uvarint():
    expr = Log(encode_uvarint(Int(500), Bytes("")))
    output = ["f403"]
    assert_output(expr, output)
