import pyteal as pt
import pytest
from algokit_utils import LogicError

import beaker as bkr
from beaker.lib.storage.blob import blob_page_size
from beaker.lib.storage.local_blob import LocalBlob

from tests.helpers import UnitTestingApp, assert_output


class LocalBlobTestState:
    lb = bkr.ReservedLocalStateValue(pt.TealType.bytes, max_keys=16)
    blob = LocalBlob(keys=[x for x in range(10) if x % 2 == 0])


def test_local_blob_zero() -> None:
    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            (s := pt.abi.String()).set(app.state.blob.read(pt.Int(0), pt.Int(64))),
            output.decode(s.encode()),
        )

    expected = list(bytes(64))
    assert_output(app, [], [expected])


def test_local_blob_write_read() -> None:
    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            app.state.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(app.state.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])


def test_local_blob_write_read_boundary() -> None:
    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(pt.Int(0)),
            app.state.blob.write(pt.Int(0), pt.BytesZero(pt.Int(blob_page_size * 3))),
            (s := pt.abi.String()).set(app.state.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))
    assert_output(app, [], [expected])


def test_local_blob_write_read_past_end() -> None:
    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            app.state.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(
                app.state.blob.read(pt.Int(0), app.state.blob.max_bytes)
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))

    with pytest.raises(LogicError):
        assert_output(app, [], [expected])


def test_local_blob_set_get() -> None:
    num = 123

    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            app.state.blob.set_byte(pt.Int(32), pt.Int(num)),
            output.set(app.state.blob.get_byte(pt.Int(32))),
        )

    expected = [num]
    assert_output(app, [], expected)


def test_local_blob_set_past_end() -> None:
    num = 123

    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            app.state.blob.set_byte(app.state.blob.max_bytes, pt.Int(num)),
            output.set(app.state.blob.get_byte(pt.Int(32))),
        )

    expected = [num]

    with pytest.raises(LogicError):
        assert_output(app, [], expected)


def test_local_blob_single_subroutine() -> None:
    app = UnitTestingApp(name="LB", state=LocalBlobTestState())

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            app.state.blob.zero(),
            app.state.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            app.state.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            pt.Pop(app.state.blob.read(pt.Int(32), pt.Int(40))),
            (s := pt.abi.String()).set(app.state.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    program = app.build().approval_program
    assert program
    assert program.count("write_impl") == 1
    assert program.count("read_impl") == 1

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])
