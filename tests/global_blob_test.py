import pytest
import pyteal as pt
import beaker as bkr

from tests.helpers import UnitTestingApp, assert_output

from beaker.lib.storage.global_blob import GlobalBlob
from beaker.lib.storage.blob import blob_page_size


class GlobalBlobState:
    lb = bkr.ReservedApplicationStateValue(pt.TealType.bytes, max_keys=64)
    blob = GlobalBlob()


def GlobalBlobTest(name: str) -> bkr.Application[GlobalBlobState]:
    return UnitTestingApp(name=name, state=GlobalBlobState())


def test_global_blob_zero() -> None:
    app = GlobalBlobTest("LBZero")

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            (s := pt.abi.String()).set(
                GlobalBlobState.blob.read(pt.Int(0), pt.Int(64))
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(64))
    assert_output(app, [], [expected], opups=1)


def test_global_blob_write_read() -> None:
    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(
                GlobalBlobState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    expected = list(b"deadbeef")
    assert_output(app, [], [expected], opups=1)


def test_global_blob_write_read_boundary() -> None:
    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.write(pt.Int(0), pt.BytesZero(pt.Int(381))),
            (s := pt.abi.String()).set(
                GlobalBlobState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))
    assert_output(app, [], [expected], opups=1)


def test_global_blob_write_read_past_end() -> None:
    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(
                GlobalBlobState.blob.read(pt.Int(0), pt.Int(blob_page_size * 64))
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], [expected], opups=1)


def test_global_blob_set_get() -> None:
    num = 123

    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.set_byte(pt.Int(32), pt.Int(num)),
            output.set(GlobalBlobState.blob.get_byte(pt.Int(32))),
        )

    expected = [num]
    assert_output(app, [], expected)


def test_global_blob_set_past_end() -> None:
    num = 123

    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.set_byte(pt.Int(blob_page_size * 64), pt.Int(num)),
            output.set(GlobalBlobState.blob.get_byte(pt.Int(32))),
        )

    expected = [num]

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], expected, opups=1)


def test_global_blob_single_subroutine() -> None:
    app = GlobalBlobTest("LB")

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            GlobalBlobState.blob.zero(),
            GlobalBlobState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            GlobalBlobState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            # Call read multiple times, in an earlier ver
            pt.Pop(GlobalBlobState.blob.read(pt.Int(32), pt.Int(40))),
            pt.Pop(GlobalBlobState.blob.read(pt.Int(32), pt.Int(40))),
            (s := pt.abi.String()).set(
                GlobalBlobState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    program = app.build().approval_program
    assert program
    assert program.count("write_impl") == 1
    assert program.count("read_impl") == 1

    expected = list(b"deadbeef")
    assert_output(app, [], [expected], opups=1)
