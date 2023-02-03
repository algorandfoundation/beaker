import pytest
import pyteal as pt
from pyteal import Bytes

from beaker.application import Application, precompiled, this_app
from beaker.client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client
from beaker.logic_signature import LogicSignature, LogicSignatureTemplate
from beaker.precompile import (
    AppPrecompile,
    LSigPrecompile,
    LSigTemplatePrecompile,
    py_encode_uvarint,
)


def test_precompile_basic():
    def Lsig(version: int) -> LogicSignature:
        def evaluate():
            return pt.Seq(pt.Assert(pt.Int(1)), pt.Int(1))

        return LogicSignature(evaluate, avm_version=version)

    app = Application()

    lsig = Lsig(version=6)

    @app.external
    def check_it():
        lsig_pc = precompiled(lsig)
        return pt.Assert(pt.Txn.sender() == lsig_pc.logic.address())

    assert app.approval_program is None
    assert app.clear_program is None
    assert len(list(app.lsig_precompiles)) == 0

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert len(list(app.lsig_precompiles)) == 1
    assert next(iter(app.lsig_precompiles)).logic.binary is not None


TMPL_BYTE_VALS = [
    ("abc"),
    ("asdfasdfasdf"),
    (bytes(100)),
    ("的的的的的的的"),
]


@pytest.mark.parametrize("tmpl_val", TMPL_BYTE_VALS)
def test_templated_bytes(tmpl_val: str):
    def Lsig(version: int) -> LogicSignatureTemplate:
        return LogicSignatureTemplate(
            lambda tv: pt.Seq(pt.Assert(pt.Len(tv)), pt.Int(1)),
            runtime_template_variables={"tv": pt.TealType.bytes},
            avm_version=version,
        )

    class App(Application):
        pc: LSigTemplatePrecompile

    app = App()

    @app.external
    def check_it() -> pt.Expr:
        app.pc = app.precompiled(Lsig(version=6))

        return pt.Assert(
            pt.Txn.sender() == app.pc.logic.template_address(tv=pt.Bytes(tmpl_val))
        )

    assert app.approval_program is None
    assert app.clear_program is None
    assert not hasattr(app, "pc")

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert ac.app.pc.logic.binary_hash is not None  # type: ignore

    populated_teal = app.pc.logic.populate_template(tv=tmpl_val)

    vlen = len(tmpl_val)
    if type(tmpl_val) is str:
        vlen = len(tmpl_val.encode("utf-8"))

    assert len(populated_teal) == len(app.pc.logic.raw_binary) + vlen + (
        len(py_encode_uvarint(vlen)) - 1
    )


TMPL_INT_VALS = [(10), (1000), (int(2.9e9))]


@pytest.mark.parametrize("tmpl_val", TMPL_INT_VALS)
def test_templated_ints(tmpl_val: int):
    def Lsig(version: int) -> LogicSignatureTemplate:
        def evaluate(tv: pt.Expr) -> pt.Seq:
            return pt.Seq(pt.Assert(tv), pt.Int(1))

        return LogicSignatureTemplate(
            evaluate,
            runtime_template_variables={"tv": pt.TealType.uint64},
            avm_version=version,
        )

    class App(Application):
        pc: LSigTemplatePrecompile

    app = App()

    @app.external
    def check_it() -> pt.Expr:
        self = this_app()
        self.pc = pc = self.precompiled(Lsig(version=6))  # type: ignore[attr-defined]
        return pt.Assert(
            pt.Txn.sender() == pc.logic.template_address(tv=pt.Int(tmpl_val))
        )

    assert app.approval_program is None
    assert app.clear_program is None
    assert not hasattr(app, "pc")

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert ac.app.pc.logic.binary_hash is not None  # type: ignore

    populated_teal = app.pc.logic.populate_template(tv=tmpl_val)

    assert len(populated_teal) == len(app.pc.logic.raw_binary) + (
        len(py_encode_uvarint(tmpl_val)) - 1
    )


def InnerLsig() -> LogicSignatureTemplate:
    def evaluate():
        return pt.Approve()

    return LogicSignatureTemplate(
        evaluate(),
        runtime_template_variables={"nonce": pt.TealType.bytes},
    )


class InnerApp(Application):
    pass


class OuterApp(Application):
    child: AppPrecompile
    lsig: LSigTemplatePrecompile

    def __init__(self):
        super().__init__()

        @self.external
        def doit(nonce: pt.abi.DynamicBytes, *, output: pt.abi.Uint64):
            self.child = child = self.precompiled(InnerApp())
            self.lsig = lsig = self.precompiled(InnerLsig())
            return pt.Seq(
                pt.Assert(
                    pt.Txn.sender() == lsig.logic.template_address(nonce=nonce.get())
                ),
                pt.InnerTxnBuilder.Execute(
                    {
                        pt.TxnField.type_enum: pt.TxnType.ApplicationCall,
                        pt.TxnField.approval_program: child.approval.binary,
                        pt.TxnField.clear_state_program: child.clear.binary,
                        pt.TxnField.fee: pt.Int(0),
                    }
                ),
                output.set(pt.InnerTxn.created_application_id()),
            )


def test_nested_precompile():
    oa = OuterApp()

    # Nothing is available until we build out the app and all its precompiles
    assert not hasattr(oa, "child")
    assert not hasattr(oa, "lsig")
    # assert oa.child.approval.teal is not None
    # assert oa.child.clear.teal is not None
    # assert oa.lsig.logic.teal is not None
    #
    # assert oa.child.approval.raw_binary is None
    # assert oa.child.clear.raw_binary is None
    # assert oa.lsig.logic.raw_binary is None

    ac = ApplicationClient(
        client=get_algod_client(), app=oa, signer=get_accounts().pop().signer
    )
    ac.build()

    assert ac.approval_binary

    assert oa.child.approval.raw_binary is not None
    assert oa.child.clear.raw_binary is not None
    assert oa.lsig.logic.raw_binary is not None

    assert len(oa.lsig.logic._template_values) == 1


def test_build_recursive():
    app = OuterApp()
    client = get_algod_client()
    pc = AppPrecompile(app, client)
    _check_app_precompiles(pc)


def LargeApp() -> Application:
    longBytes = 4092 * b"A"
    longBytes2 = 2048 * b"A"

    app = Application(name="LargeApp")

    @app.external
    def compare_big_byte_strings():
        return pt.Assert(pt.Bytes(longBytes) != pt.Bytes(longBytes2))

    return app


def test_large_app_create():
    class LargeAppDeployer(Application):
        def __init__(self):
            super().__init__()

            la = LargeApp()

            @self.external
            def deploy_large_app(*, output: pt.abi.Uint64):
                large_app = self.precompiled(la)
                return pt.Seq(
                    pt.InnerTxnBuilder.Execute(large_app.get_create_config()),
                    output.set(pt.InnerTxn.application_id()),
                )

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), LargeAppDeployer(), signer=acct.signer)

    ac.create()
    ac.fund(1_000_000)
    result = ac.call("deploy_large_app")
    print(result.return_value)


def test_page_hash():
    class SmallApp(Application):
        pass

    small_precompile = AppPrecompile(SmallApp(), get_algod_client())
    _check_app_precompiles(small_precompile)


def test_extra_page_population():

    app = LargeApp()
    app_precompile = AppPrecompile(app, get_algod_client())
    _check_app_precompiles(app_precompile)

    assert app_precompile.approval.program_pages is not None
    assert app_precompile.clear.program_pages is not None
    recovered_approval_binary = b""
    for approval_page in app_precompile.approval.program_pages:
        assert isinstance(approval_page, Bytes)
        recovered_approval_binary += bytes.fromhex(approval_page.byte_str)

    recovered_clear_binary = b""
    for clear_page in app_precompile.clear.program_pages:
        assert isinstance(clear_page, Bytes)
        recovered_clear_binary += bytes.fromhex(clear_page.byte_str)

    assert recovered_approval_binary == app_precompile.approval.raw_binary
    assert recovered_clear_binary == app_precompile.clear.raw_binary


def _check_app_precompiles(app_precompile: AppPrecompile):
    for p in app_precompile.app.precompiles:
        match p:
            case LSigPrecompile():
                _check_lsig_precompiles(p)
            case AppPrecompile():
                _check_app_precompiles(p)
            case LSigTemplatePrecompile():
                _check_lsig_template_precompiles(p)

    assert app_precompile.approval.teal != ""
    assert app_precompile.approval.raw_binary is not None
    assert app_precompile.approval.binary.byte_str != b""
    assert app_precompile.approval.source_map is not None
    assert app_precompile.approval.binary_hash is not None

    assert len(app_precompile.approval.program_pages) > 0

    assert app_precompile.clear.teal != ""
    assert app_precompile.clear.raw_binary is not None
    assert app_precompile.clear.binary.byte_str != b""
    assert app_precompile.clear.source_map is not None
    assert app_precompile.clear.binary_hash is not None
    assert len(app_precompile.clear.program_pages) > 0


def _check_lsig_precompiles(lsig_precompile: LSigPrecompile):
    assert lsig_precompile.logic.teal != ""
    assert lsig_precompile.logic.raw_binary is not None
    assert lsig_precompile.logic.binary.byte_str != b""
    assert lsig_precompile.logic.source_map is not None
    assert lsig_precompile.logic.binary_hash is not None
    if isinstance(lsig_precompile.lsig, LogicSignatureTemplate):
        assert len(lsig_precompile.logic._template_values) == len(
            lsig_precompile.lsig.template_variables
        )
    else:
        assert lsig_precompile.logic.address()


def _check_lsig_template_precompiles(lsig_precompile: LSigTemplatePrecompile):
    assert lsig_precompile.logic.teal != ""
    assert lsig_precompile.logic.raw_binary is not None
    assert lsig_precompile.logic.binary.byte_str != b""
    assert lsig_precompile.logic.source_map is not None
    assert lsig_precompile.logic.binary_hash is not None
    if isinstance(lsig_precompile.lsig, LogicSignatureTemplate):
        assert len(lsig_precompile.logic._template_values) == len(
            lsig_precompile.lsig.template_variables
        )
    else:
        assert lsig_precompile.logic.address()
