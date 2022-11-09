import pytest
import pyteal as pt
from .mapping import Mapping, MapElement
from beaker.application import Application
from beaker.decorators import external


options = pt.CompileOptions(version=pt.MAX_TEAL_VERSION, mode=pt.Mode.Application)


def test_mapping():
    m = Mapping(pt.abi.Address, pt.abi.Uint64)
    assert m._key_type == pt.abi.Address
    assert m._key_type_spec == pt.abi.AddressTypeSpec()

    assert m._value_type == pt.abi.Uint64
    assert m._value_type_spec == pt.abi.Uint64TypeSpec()

    with pytest.raises(pt.TealTypeError):
        m[pt.abi.String()]

    with pytest.raises(pt.TealTypeError):
        m[pt.Int(1)]

    item = m[pt.Txn.sender()]
    assert isinstance(item, MapElement)

    expected, _ = pt.Seq(
        bx := pt.BoxGet(pt.Txn.sender()), pt.Assert(bx.hasValue()), bx.value()
    ).__teal__(options)
    actual, _ = item.get().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    v = pt.abi.Uint64()
    expected, _ = v.decode(
        pt.Seq(bx := pt.BoxGet(pt.Txn.sender()), pt.Assert(bx.hasValue()), bx.value())
    ).__teal__(options)
    actual, _ = item.store_into(v).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    expected, _ = pt.Seq(
        pt.Pop(pt.BoxDelete(pt.Txn.sender())), pt.BoxPut(pt.Txn.sender(), v.encode())
    ).__teal__(options)
    actual, _ = item.set(v).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        item.set(pt.abi.String())


def test_app_mapping():
    class T(Application):
        m = Mapping(pt.abi.Address, pt.abi.Uint64)

        @external
        def thing(self, name: pt.abi.Address, *, output: pt.abi.Uint64):
            return self.m[name].store_into(output)

    t = T()
    assert len(t.approval_program) > 0
