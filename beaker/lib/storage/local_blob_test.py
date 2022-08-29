import pytest
import pyteal as pt
import beaker as bkr

from beaker.testing import UnitTestingApp, assert_output

from beaker.lib.storage.local_blob import LocalBlob
from beaker.lib.storage.blob import blob_page_size


class LocalBlobTest(UnitTestingApp):
    lb = bkr.DynamicAccountStateValue(pt.TealType.bytes, max_keys=16)
    blob = LocalBlob(keys=[x for x in range(10) if x % 2 == 0])


def test_local_blob_zero():
    class LBZero(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(0), pt.Int(64))),
                output.decode(s.encode()),
            )

    expected = list(bytes(64))
    assert_output(LBZero(), [], [expected])


def test_local_blob_write_read():
    class LB(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                self.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(32), pt.Int(40))),
                output.decode(s.encode()),
            )

    expected = list(b"deadbeef")
    assert_output(LB(), [], [expected])


def test_local_blob_write_read_boundary():
    class LB(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(pt.Int(0)),
                self.blob.write(pt.Int(0), pt.BytesZero(pt.Int(blob_page_size * 3))),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(32), pt.Int(40))),
                output.decode(s.encode()),
            )

    expected = list(bytes(8))
    assert_output(LB(), [], [expected])


def test_local_blob_write_read_past_end():
    class LB(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                self.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
                (s := pt.abi.String()).set(
                    self.blob.read(pt.Int(0), self.blob.max_bytes)
                ),
                output.decode(s.encode()),
            )

    expected = list(bytes(8))

    with pytest.raises(bkr.client.LogicException):
        assert_output(LB(), [], [expected])


def test_local_blob_set_get():
    num = 123

    class LB(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.Uint8):
            return pt.Seq(
                self.blob.zero(),
                self.blob.set_byte(pt.Int(32), pt.Int(num)),
                output.set(self.blob.get_byte(pt.Int(32))),
            )

    expected = [num]
    assert_output(LB(), [], expected)


def test_local_blob_set_past_end():
    num = 123

    class LB(LocalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.Uint8):
            return pt.Seq(
                self.blob.zero(),
                self.blob.set_byte(self.blob.max_bytes, pt.Int(num)),
                output.set(self.blob.get_byte(pt.Int(32))),
            )

    expected = [num]

    with pytest.raises(bkr.client.LogicException):
        assert_output(LB(), [], expected)
