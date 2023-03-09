import pyteal as pt
import pytest

from beaker import Application, consts, sandbox
from beaker.client import ApplicationClient
from beaker.lib.storage import BoxMapping

options = pt.CompileOptions(version=pt.MAX_TEAL_VERSION, mode=pt.Mode.Application)


def test_mapping() -> None:
    m = BoxMapping(pt.abi.Address, pt.abi.Uint64)
    assert m._key_type == pt.abi.Address
    assert m._key_type_spec == pt.abi.AddressTypeSpec()

    assert m._value_type == pt.abi.Uint64
    assert m._value_type_spec == pt.abi.Uint64TypeSpec()

    with pytest.raises(pt.TealTypeError):
        m[pt.abi.String()]

    with pytest.raises(pt.TealTypeError):
        m[pt.Int(1)]

    item = m[pt.Txn.sender()]
    assert isinstance(item, BoxMapping.Element)

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


def test_mapping_with_prefix() -> None:
    m = BoxMapping(pt.abi.String, pt.abi.Uint64, prefix=pt.Bytes("m_"))

    app = Application("")

    @app.external
    def do_things() -> pt.Expr:
        elem = m[pt.Bytes("a")]
        value1 = 123
        value2 = 234
        return pt.Seq(
            pt.Assert(pt.Not(elem.exists())),
            (put := pt.abi.Uint64()).set(value1),
            elem.set(put),
            pt.Assert(elem.exists()),
            elem.store_into(got := pt.abi.Uint64()),
            pt.Assert(got.get() == pt.Int(value1)),
            put.set(value2),
            elem.set(put.encode()),
            got.decode(elem.get()),
            pt.Assert(got.get() == pt.Int(value2)),
            pt.Assert(elem.delete()),
            pt.Assert(pt.Not(elem.exists())),
        )

    app_client = ApplicationClient(
        sandbox.get_algod_client(), app, signer=sandbox.get_accounts()[0].signer
    )
    app_client.create()

    app_client.fund(1 * consts.algo)

    app_client.call(do_things, boxes=[(app_client.app_id, "m_a")])


def test_mapping_with_set_resize() -> None:
    m = BoxMapping(pt.abi.String, pt.abi.String, prefix=pt.Bytes("m_"))

    app = Application("")

    @app.external
    def do_things() -> pt.Expr:
        elem = m[pt.Bytes("a")]
        value1 = "value"
        value2 = "value_value"
        return pt.Seq(
            (put := pt.abi.String()).set(value1),
            elem.set(put),
            pt.Assert(elem.exists()),
            elem.store_into(got := pt.abi.String()),
            pt.Assert(got.get() == pt.Bytes(value1)),
            put.set(value2),
            elem.set(put.encode()),
            got.decode(elem.get()),
            pt.Assert(got.get() == pt.Bytes(value2)),
        )

    app_client = ApplicationClient(
        sandbox.get_algod_client(), app, signer=sandbox.get_accounts()[0].signer
    )
    app_client.create()

    app_client.fund(1 * consts.algo)

    app_client.call(do_things, boxes=[(app_client.app_id, "m_a")])


def test_mapping_with_bad_prefix() -> None:
    with pytest.raises(pt.TealTypeError):
        BoxMapping(pt.abi.String, pt.abi.Uint64, prefix=pt.Int(1))


def test_mapping_set_value_bad_type() -> None:
    m = BoxMapping(pt.abi.String, pt.abi.Uint64)
    elem = m[pt.Bytes("key")]
    with pytest.raises(pt.TealTypeError):
        elem.set(pt.abi.Uint16().set(123))

    with pytest.raises(pt.TealTypeError):
        elem.set(b"123")  # type: ignore


def test_mapping_get_key_bad_type() -> None:
    m = BoxMapping(pt.abi.String, pt.abi.Uint64)

    with pytest.raises(pt.TealTypeError):
        m[b"123"].exists()  # type: ignore


def test_app_mapping() -> None:
    class State:
        m = BoxMapping(pt.abi.Address, pt.abi.Uint64)

    t = Application("T", state=State())

    @t.external
    def thing(name: pt.abi.Address, *, output: pt.abi.Uint64) -> pt.Expr:
        return t.state.m[name].store_into(output)

    compiled = t.build()
    assert compiled.approval_program
