import pytest
import pyteal as pt
from beaker.application import Application
from beaker.decorators import external
from beaker.client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client

from beaker.logic_signature import LogicSignature, TemplateVariable

from beaker.precompile import Precompile, py_encode_uvarint


def test_precompile():
    class App(Application):
        class Lsig(LogicSignature):
            def evaluate(self):
                return pt.Seq(pt.Assert(pt.Int(1)), pt.Int(1))

        pc = Precompile(Lsig(version=6))

        @external
        def check_it(self):
            return pt.Assert(pt.Txn.sender() == self.pc.address())

    app = App()
    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.addr is None

    ac.build()

    assert app.approval_program is not None
    assert app.clear_program is not None
    assert app.pc.addr is not None


TMPL_BYTE_VALS = [
    ("abc"),
    ("asdfasdfasdf"),
    (bytes(100)),
    ("的的的的的的的"),
]


@pytest.mark.parametrize("tmpl_val", TMPL_BYTE_VALS)
def test_templated_bytes(tmpl_val: str):
    class Lsig(LogicSignature):
        tv = TemplateVariable(pt.TealType.bytes)

        def evaluate(self):
            return pt.Seq(pt.Assert(pt.Len(self.tv)), pt.Int(1))

    class App(Application):
        pc = Precompile(Lsig(version=6))

        @external
        def check_it(self):
            return pt.Assert(
                pt.Txn.sender() == self.pc.template_address(pt.Bytes(tmpl_val))
            )

    app = App()
    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.addr is None

    ac.build()

    assert app.approval_program is not None
    assert app.clear_program is not None
    assert app.pc.addr is not None

    populated_teal = app.pc.populate_template(tmpl_val)

    vlen = len(tmpl_val)
    if type(tmpl_val) is str:
        vlen = len(tmpl_val.encode("utf-8"))

    assert len(populated_teal) == len(app.pc.binary) + vlen + (
        len(py_encode_uvarint(vlen)) - 1
    )


TMPL_INT_VALS = [(10), (1000), (int(2.9e9))]


@pytest.mark.parametrize("tmpl_val", TMPL_INT_VALS)
def test_templated_ints(tmpl_val: int):
    class Lsig(LogicSignature):
        tv = TemplateVariable(pt.TealType.uint64)

        def evaluate(self):
            return pt.Seq(pt.Assert(self.tv), pt.Int(1))

    class App(Application):
        pc = Precompile(Lsig(version=6))

        @external
        def check_it(self):
            return pt.Assert(
                pt.Txn.sender() == self.pc.template_address(pt.Int(tmpl_val))
            )

    app = App()
    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.addr is None

    ac.build()

    assert app.approval_program is not None
    assert app.clear_program is not None
    assert app.pc.addr is not None

    populated_teal = app.pc.populate_template(tmpl_val)

    assert len(populated_teal) == len(app.pc.binary) + (
        len(py_encode_uvarint(tmpl_val)) - 1
    )
