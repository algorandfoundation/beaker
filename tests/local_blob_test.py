import pytest
import pyteal as pt
import beaker as bkr

from beaker.testing import UnitTestingApp, assert_output

from beaker.lib.storage.local_blob import LocalBlob
from beaker.lib.storage.blob import blob_page_size


class LocalBlobTest(UnitTestingApp):
    lb = bkr.ReservedAccountStateValue(pt.TealType.bytes, max_keys=16)
    blob = LocalBlob(keys=[x for x in range(10) if x % 2 == 0])


def test_local_blob_zero():
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]):
        return pt.Seq(
            app.blob.zero(),
            (s := pt.abi.String()).set(app.blob.read(pt.Int(0), pt.Int(64))),
            output.decode(s.encode()),
        )

    expected = list(bytes(64))
    assert_output(app, [], [expected])


def test_local_blob_write_read():
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]):
        return pt.Seq(
            app.blob.zero(),
            app.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(app.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])


def test_local_blob_write_read_boundary():
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]):
        return pt.Seq(
            app.blob.zero(pt.Int(0)),
            app.blob.write(pt.Int(0), pt.BytesZero(pt.Int(blob_page_size * 3))),
            (s := pt.abi.String()).set(app.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))
    assert_output(app, [], [expected])


def test_local_blob_write_read_past_end():
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]):
        return pt.Seq(
            app.blob.zero(),
            app.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            (s := pt.abi.String()).set(app.blob.read(pt.Int(0), app.blob.max_bytes)),
            output.decode(s.encode()),
        )

    expected = list(bytes(8))

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], [expected])


def test_local_blob_set_get():
    num = 123

    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.Uint8):
        return pt.Seq(
            app.blob.zero(),
            app.blob.set_byte(pt.Int(32), pt.Int(num)),
            output.set(app.blob.get_byte(pt.Int(32))),
        )

    expected = [num]
    assert_output(app, [], expected)


def test_local_blob_set_past_end():
    num = 123

    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.Uint8):
        return pt.Seq(
            app.blob.zero(),
            app.blob.set_byte(app.blob.max_bytes, pt.Int(num)),
            output.set(app.blob.get_byte(pt.Int(32))),
        )

    expected = [num]

    with pytest.raises(bkr.client.LogicException):
        assert_output(app, [], expected)


def test_local_blob_single_subroutine():
    app = LocalBlobTest()

    @app.external
    def unit_test(*, output: pt.abi.DynamicArray[pt.abi.Byte]):
        return pt.Seq(
            app.blob.zero(),
            app.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            app.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
            pt.Pop(app.blob.read(pt.Int(32), pt.Int(40))),
            (s := pt.abi.String()).set(app.blob.read(pt.Int(32), pt.Int(40))),
            output.decode(s.encode()),
        )

    app.compile()
    program = app.approval_program
    assert program
    assert program.count("write_impl") == 1
    assert program.count("read_impl") == 1

    expected = list(b"deadbeef")
    assert_output(app, [], [expected])
