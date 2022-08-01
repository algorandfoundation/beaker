from pyteal import Bytes, BytesZero, Int, Itob, Log, Pop, Seq

from tests.helpers import (
    LOGIC_EVAL_ERROR,
    assert_fail,
    assert_stateful_fail,
    assert_stateful_output,
    logged_bytes,
    logged_int,
)

from .local_blob import LocalBlob, max_bytes

# Can re-use the same blob
b = LocalBlob()


def test_local_blob_zero():
    expr = Seq(b.zero(Int(0)), Log(b.read(Int(0), Int(0), Int(64))))
    expected = [logged_int(0) * 8]
    assert_stateful_output(expr, expected)


def test_local_blob_no_schema():
    expr = Seq(b.zero(Int(0)), Log(b.read(Int(0), Int(0), Int(64))))
    expected = [LOGIC_EVAL_ERROR]
    assert_fail(expr, expected)


def test_local_blob_write_read():
    expr = Seq(
        b.zero(Int(0)),
        Pop(b.write(Int(0), Int(0), Bytes("deadbeef" * 8))),
        Log(b.read(Int(0), Int(32), Int(40))),
    )
    expected = [logged_bytes("deadbeef")]
    assert_stateful_output(expr, expected)


def test_local_blob_write_read_boundary():
    expr = Seq(
        b.zero(Int(0)),
        Pop(b.write(Int(0), Int(0), BytesZero(Int(381)))),
        Log(b.read(Int(0), Int(32), Int(40))),
    )
    expected = ["00" * 8]
    assert_stateful_output(expr, expected)


def test_local_blob_write_read_no_zero():
    expr = Seq(
        Pop(b.write(Int(0), Int(0), Bytes("deadbeef" * 8))),
        Log(b.read(Int(0), Int(32), Int(40))),
    )
    expected = [LOGIC_EVAL_ERROR]
    assert_stateful_fail(expr, expected)


def test_local_blob_write_read_past_end():
    expr = Seq(
        b.zero(Int(0)),
        Pop(b.write(Int(0), Int(0), Bytes("deadbeef" * 8))),
        Log(b.read(Int(0), Int(0), max_bytes)),
    )
    expected = [LOGIC_EVAL_ERROR]
    assert_stateful_fail(expr, expected)


def test_local_blob_set_get():
    expr = Seq(
        b.zero(Int(0)),
        b.set_byte(Int(0), Int(32), Int(123)),
        Log(Itob(b.get_byte(Int(0), Int(32)))),
    )
    expected = [logged_int(123)]
    assert_stateful_output(expr, expected)


def test_local_blob_set_past_end():
    expr = Seq(
        b.zero(Int(0)),
        b.set_byte(Int(0), max_bytes, Int(123)),
        Log(Itob(b.get_byte(Int(0), Int(32)))),
    )
    expected = [LOGIC_EVAL_ERROR]
    assert_stateful_fail(expr, expected)
