import pytest
import pyteal as pt
import beaker as bkr

from beaker.testing.unit_testing_helpers import UnitTestingApp, assert_output

from beaker.lib.storage.global_blob import GlobalBlob
from beaker.lib.storage.blob import blob_page_size


class GlobalBlobTest(UnitTestingApp):
    lb = bkr.DynamicApplicationStateValue(pt.TealType.bytes, max_keys=64)
    blob = GlobalBlob()


def test_global_blob_zero():
    class LBZero(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(0), pt.Int(64))),
                output.decode(s.encode()),
            )

    expected = list(bytes(64))
    assert_output(LBZero(), [], [expected], opups=1)


def test_global_blob_write_read():
    class LB(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                self.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(32), pt.Int(40))),
                output.decode(s.encode()),
            )

    expected = list(b"deadbeef")
    assert_output(LB(), [], [expected], opups=1)


def test_global_blob_write_read_boundary():
    class LB(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                self.blob.write(pt.Int(0), pt.BytesZero(pt.Int(381))),
                (s := pt.abi.String()).set(self.blob.read(pt.Int(32), pt.Int(40))),
                output.decode(s.encode()),
            )

    expected = list(bytes(8))
    assert_output(LB(), [], [expected], opups=1)


def test_global_blob_write_read_past_end():
    class LB(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.DynamicArray[pt.abi.Byte]):
            return pt.Seq(
                self.blob.zero(),
                self.blob.write(pt.Int(0), pt.Bytes("deadbeef" * 8)),
                (s := pt.abi.String()).set(
                    self.blob.read(pt.Int(0), pt.Int(blob_page_size * 64))
                ),
                output.decode(s.encode()),
            )

    expected = list(bytes(8))

    with pytest.raises(bkr.client.LogicException):
        assert_output(LB(), [], [expected], opups=1)


def test_global_blob_set_get():
    num = 123

    class LB(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.Uint8):
            return pt.Seq(
                self.blob.zero(),
                self.blob.set_byte(pt.Int(32), pt.Int(num)),
                output.set(self.blob.get_byte(pt.Int(32))),
            )

    expected = [num]
    assert_output(LB(), [], expected)


def test_global_blob_set_past_end():
    num = 123

    class LB(GlobalBlobTest):
        @bkr.external
        def unit_test(self, *, output: pt.abi.Uint8):
            return pt.Seq(
                self.blob.zero(),
                self.blob.set_byte(pt.Int(blob_page_size * 64), pt.Int(num)),
                output.set(self.blob.get_byte(pt.Int(32))),
            )

    expected = [num]

    with pytest.raises(bkr.client.LogicException):
        assert_output(LB(), [], expected, opups=1)
