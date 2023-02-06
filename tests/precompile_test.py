import pytest
import pyteal as pt
from pyteal import Bytes

from beaker.application import (
    Application,
    precompiled,
    this_app,
)
from beaker.blueprints import unconditional_create_approval
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

    app = Application("BasicPrecompile")

    lsig = Lsig(version=6)

    @app.external
    def check_it():
        lsig_pc = precompiled(lsig)
        return pt.Assert(pt.Txn.sender() == lsig_pc.address())

    assert app.approval_program is None
    assert app.clear_program is None
    assert app._lsig_precompiles == {}

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    lsig_pc = app._lsig_precompiles.get(lsig)
    assert lsig_pc is not None
    assert lsig_pc.logic.binary is not None


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

    pc: LSigTemplatePrecompile | None = None

    app = Application("App")

    @app.external
    def check_it() -> pt.Expr:
        nonlocal pc
        pc = app.precompiled(Lsig(version=6))
        return pt.Assert(pt.Txn.sender() == pc.address(tv=pt.Bytes(tmpl_val)))

    assert app.approval_program is None
    assert app.clear_program is None
    assert pc is None

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert pc is not None
    assert pc.logic.binary_hash is not None

    populated_teal = pc.logic.populate_template(tv=tmpl_val)

    vlen = len(tmpl_val)
    if type(tmpl_val) is str:
        vlen = len(tmpl_val.encode("utf-8"))

    assert len(populated_teal) == len(pc.logic.raw_binary) + vlen + (
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

    pc: LSigTemplatePrecompile | None = None

    app = Application("App")

    @app.external
    def check_it() -> pt.Expr:
        nonlocal pc
        pc = this_app().precompiled(Lsig(version=6))
        return pt.Assert(pt.Txn.sender() == pc.address(tv=pt.Int(tmpl_val)))

    assert app.approval_program is None
    assert app.clear_program is None
    assert pc is None

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    ac.build()

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert pc is not None
    assert pc.logic.binary_hash is not None

    populated_teal = pc.logic.populate_template(tv=tmpl_val)

    assert len(populated_teal) == len(pc.logic.raw_binary) + (
        len(py_encode_uvarint(tmpl_val)) - 1
    )


inner_app = Application("InnerApp").implement(unconditional_create_approval)
inner_lsig = LogicSignatureTemplate(
    pt.Approve(),
    runtime_template_variables={"nonce": pt.TealType.bytes},
)


def OuterApp() -> Application:

    app = Application("OuterApp")

    @app.external
    def doit(nonce: pt.abi.DynamicBytes, *, output: pt.abi.Uint64):
        child = precompiled(inner_app)
        lsig = precompiled(inner_lsig)
        return pt.Seq(
            pt.Assert(pt.Txn.sender() == lsig.address(nonce=nonce.get())),
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

    return app


def test_nested_precompile():
    oa = OuterApp()

    # Nothing is available until we build out the app and all its precompiles
    assert oa._app_precompiles == {}
    assert oa._lsig_precompiles == {}
    assert oa._lsig_template_precompiles == {}

    ac = ApplicationClient(
        client=get_algod_client(), app=oa, signer=get_accounts().pop().signer
    )
    ac.build()

    assert ac.approval_binary

    child = oa._app_precompiles.get(inner_app)
    assert child is not None
    lsig = oa._lsig_template_precompiles.get(inner_lsig)
    assert lsig is not None

    assert child.approval.raw_binary is not None
    assert child.clear.raw_binary is not None
    assert lsig.logic.raw_binary is not None

    assert len(lsig.logic._template_values) == 1


def test_build_recursive():
    app = OuterApp()
    client = get_algod_client()
    pc = AppPrecompile(app, client)
    _check_app_precompiles(pc)


def LargeApp() -> Application:
    longBytes = 4092 * b"A"
    longBytes2 = 2048 * b"A"

    app = Application(name="LargeApp").implement(unconditional_create_approval)

    @app.external
    def compare_big_byte_strings():
        return pt.Assert(pt.Bytes(longBytes) != pt.Bytes(longBytes2))

    return app


def test_large_app_create():
    la = LargeApp()

    deployer = Application("LargeAppDeployer").implement(unconditional_create_approval)

    @deployer.external
    def deploy_large_app(*, output: pt.abi.Uint64):
        large_app = precompiled(la)
        return pt.Seq(
            pt.InnerTxnBuilder.Execute(large_app.get_create_config()),
            output.set(pt.InnerTxn.application_id()),
        )

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), deployer, signer=acct.signer)

    ac.create()
    ac.fund(1_000_000)
    result = ac.call("deploy_large_app")
    print(result.return_value)


def test_page_hash():
    small_precompile = AppPrecompile(Application("SmallApp"), get_algod_client())
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
    for lp in app_precompile.app._lsig_precompiles.values():
        _check_lsig_precompiles(lp)
    for ap in app_precompile.app._app_precompiles.values():
        _check_app_precompiles(ap)
    for ltp in app_precompile.app._lsig_template_precompiles.values():
        _check_lsig_template_precompiles(ltp)

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
    assert lsig_precompile.address()


def _check_lsig_template_precompiles(lsig_precompile: LSigTemplatePrecompile):
    assert lsig_precompile.logic.teal != ""
    assert lsig_precompile.logic.raw_binary is not None
    assert lsig_precompile.logic.binary.byte_str != b""
    assert lsig_precompile.logic.source_map is not None
    assert lsig_precompile.logic.binary_hash is not None
    assert (
        lsig_precompile.logic._template_values.keys()
        == lsig_precompile.lsig.runtime_template_variables.keys()
    )
