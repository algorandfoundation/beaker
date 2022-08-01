from algosdk.future.transaction import StateSchema
from pyteal import Bytes, BytesZero, Int, Itob, Log, Pop, Seq

from tests.helpers import (
    LOGIC_EVAL_ERROR,
    assert_fail,
    assert_output,
    logged_bytes,
    logged_int,
)

from .global_blob import GlobalBlob, max_bytes

# Can re-use the same blob
b = GlobalBlob()


def test_global_blob_zero():
    expr = Seq(b.zero(), Log(b.read(Int(0), Int(64))))
    expected = [logged_int(0) * 8]
    assert_output(expr, expected, global_schema=StateSchema(0, 64))


def test_global_blob_zero_no_schema():
    expr = Seq(b.zero(), Log(b.read(Int(0), Int(64))))
    # Not providing the required schema
    expected = [LOGIC_EVAL_ERROR]
    assert_fail(expr, expected)


def test_global_blob_write_read():
    expr = Seq(
        b.zero(),
        Pop(b.write(Int(0), Bytes("deadbeef" * 2))),
        Log(b.read(Int(0), Int(8))),
    )
    expected = [logged_bytes("deadbeef")]
    assert_output(expr, expected, global_schema=StateSchema(0, 64), pad_budget=3)


def test_global_blob_write_read_boundary():
    expr = Seq(
        b.zero(),
        Pop(b.write(Int(0), BytesZero(Int(381)))),
        Log(b.read(Int(32), Int(40))),
    )
    expected = ["00" * 8]
    assert_output(expr, expected, global_schema=StateSchema(0, 64), pad_budget=3)


def test_global_blob_write_read_no_zero():
    expr = Seq(Pop(b.write(Int(0), Bytes("deadbeef" * 2))), Log(b.read(Int(0), Int(8))))
    expected = [LOGIC_EVAL_ERROR]
    assert_fail(expr, expected, global_schema=StateSchema(0, 64), pad_budget=3)


def test_global_blob_write_read_past_end():
    expr = Seq(
        b.zero(),
        Pop(b.write(Int(0), Bytes("deadbeef" * 2))),
        Log(b.read(Int(0), max_bytes)),
    )
    expected = [LOGIC_EVAL_ERROR]
    assert_fail(expr, expected, global_schema=StateSchema(0, 64), pad_budget=3)


def test_global_blob_set_get():
    expr = Seq(b.zero(), b.set_byte(Int(32), Int(123)), Log(Itob(b.get_byte(Int(32)))))
    expected = [logged_int(123)]
    assert_output(expr, expected, global_schema=StateSchema(0, 64))


def test_global_blob_set_past_end():
    expr = Seq(b.zero(), b.set_byte(max_bytes, Int(123)))
    expected = [LOGIC_EVAL_ERROR]
    assert_fail(expr, expected, global_schema=StateSchema(0, 64))
