from pyteal import App, Bytes, Int, Log, Seq

from tests.helpers import assert_stateful_fail, assert_stateful_output, logged_bytes

from .storage import global_get_else, global_must_get, local_get_else, local_must_get


def test_global_get_else():
    expr = Log(global_get_else(Bytes("doesn't exist"), Bytes("default")))
    expected = [logged_bytes("default")]
    assert_stateful_output(expr, expected)


def test_global_must_get():
    expr = Seq(
        App.globalPut(Bytes("exists"), Bytes("success")),
        Log(global_must_get(Bytes("exists"))),
    )
    expected = [logged_bytes("success")]
    assert_stateful_output(expr, expected)


def test_global_must_get_missing():
    expr = Log(global_must_get(Bytes("doesnt exist")))
    assert_stateful_fail(expr, ["logic eval error"])


def test_local_must_get():
    expr = Seq(
        App.localPut(Int(0), Bytes("exists"), Bytes("success")),
        Log(local_must_get(Int(0), Bytes("exists"))),
    )
    expected = [logged_bytes("success")]
    assert_stateful_output(expr, expected)


def test_local_must_get_missing():
    expr = Log(local_must_get(Int(0), Bytes("doesnt exist")))
    assert_stateful_fail(expr, ["logic eval error"])


def test_local_get_else():
    expr = Log(local_get_else(Int(0), Bytes("doesn't exist"), Bytes("default")))
    expected = [logged_bytes("default")]
    assert_stateful_output(expr, expected)
