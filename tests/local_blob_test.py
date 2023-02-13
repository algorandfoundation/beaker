import pytest
import pyteal as pt
import beaker as bkr

from tests.helpers import UnitTestingApp, assert_output

from beaker.lib.storage.local_blob import LocalBlob
from beaker.lib.storage.blob import blob_page_size


class LocalBlobTestState:
    lb = bkr.ReservedAccountStateValue(pt.TealType.bytes, max_keys=16)
    blob = LocalBlob(keys=[x for x in range(10) if x % 2 == 0])


def LocalBlobTest(name: str = "LB") -> bkr.Application[LocalBlobTestState]:
    return UnitTestingApp(name=name, state=LocalBlobTestState())


def test_local_blob_zero() -> None:
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            (s := pt.abi.String()).set(
                LocalBlobTestState.blob.read(pt.Int(0), pt.Int(64))
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(64))
    assert_output(app, [], [expected])


def test_local_blob_write_read() -> None:
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            LocalBlobTestState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(
                LocalBlobTestState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])


def test_local_blob_write_read_boundary() -> None:
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(pt.Int(0)),
            LocalBlobTestState.blob.write(
                pt.Int(0), pt.BytesZero(pt.Int(blob_page_size * 3))
            ),
            (s := pt.abi.String()).set(
                LocalBlobTestState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))
    assert_output(app, [], [expected])


def test_local_blob_write_read_past_end() -> None:
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            LocalBlobTestState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(
                LocalBlobTestState.blob.read(
                    pt.Int(0), LocalBlobTestState.blob.max_bytes
                )
            ),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], [expected])


def test_local_blob_set_get() -> None:
    num = 123

    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            LocalBlobTestState.blob.set_byte(pt.Int(32), pt.Int(num)),
            output.set(LocalBlobTestState.blob.get_byte(pt.Int(32))),
        )

    expected = [num]
    assert_output(app, [], expected)


def test_local_blob_set_past_end() -> None:
    num = 123

    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.Uint8) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            LocalBlobTestState.blob.set_byte(
                LocalBlobTestState.blob.max_bytes, pt.Int(num)
            ),
            output.set(LocalBlobTestState.blob.get_byte(pt.Int(32))),
        )

    expected = [num]

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], expected)


def test_local_blob_single_subroutine() -> None:
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]) -> pt.Expr:
        return pt.Seq(
            LocalBlobTestState.blob.zero(),
            LocalBlobTestState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            LocalBlobTestState.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            pt.Pop(LocalBlobTestState.blob.read(pt.Int(32), pt.Int(40))),
            (s := pt.abi.String()).set(
                LocalBlobTestState.blob.read(pt.Int(32), pt.Int(40))
            ),
            output.decode(s.encode()),
        )

    program = app.build().approval_program
    assert program
    assert program.count("write_impl") == 1
    assert program.count("read_impl") == 1

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])
