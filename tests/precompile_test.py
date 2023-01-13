import pytest
import pyteal as pt

from beaker.application import Application
from beaker.decorators import external
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

        return LogicSignature(evaluate, teal_version=version)

    class App(Application):
        pc = LSigPrecompile(Lsig(version=6))

        @external
        def check_it(self):
            return pt.Assert(pt.Txn.sender() == self.pc.logic.address())

    app = App()
    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.logic.binary_hash is None

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert ac._app.pc.logic.binary_hash is not None


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
            teal_version=version,
        )

    class App(Application):
        pc = LSigTemplatePrecompile(Lsig(version=6))

        @external
        def check_it(self) -> pt.Expr:
            return pt.Assert(
                pt.Txn.sender() == self.pc.logic.template_address(tv=pt.Bytes(tmpl_val))
            )

    app = App()

    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.logic.binary_hash is None

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert ac._app.pc.logic.binary_hash is not None

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
            teal_version=version,
        )

    class App(Application):
        pc = LSigTemplatePrecompile(Lsig(version=6))

        @external
        def check_it(self) -> pt.Expr:
            return pt.Assert(
                pt.Txn.sender() == self.pc.logic.template_address(tv=pt.Int(tmpl_val))
            )

    app = App()

    assert app.approval_program is None
    assert app.clear_program is None
    assert app.pc.logic.binary_hash is None

    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)

    assert ac.approval_program is not None
    assert ac.clear_program is not None
    assert ac._app.pc.logic.binary_hash is not None

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
    child: AppPrecompile = AppPrecompile(InnerApp())
    lsig: LSigPrecompile = LSigTemplatePrecompile(InnerLsig())

    @external
    def doit(self, nonce: pt.abi.DynamicBytes, *, output: pt.abi.Uint64):
        return pt.Seq(
            pt.Assert(
                pt.Txn.sender() == self.lsig.logic.template_address(nonce=nonce.get())
            ),
            pt.InnerTxnBuilder.Execute(
                {
                    pt.TxnField.type_enum: pt.TxnType.ApplicationCall,
                    pt.TxnField.approval_program: self.child.approval.binary,
                    pt.TxnField.clear_state_program: self.child.clear.binary,
                    pt.TxnField.fee: pt.Int(0),
                }
            ),
            output.set(pt.InnerTxn.created_application_id()),
        )


def test_nested_precompile():
    oa = OuterApp()

    # Nothing is available until we build out the app and all its precompiles
    assert oa.child.approval.teal is not None
    assert oa.child.clear.teal is not None
    assert oa.lsig.logic.teal is not None

    assert oa.child.approval.raw_binary is None
    assert oa.child.clear.raw_binary is None
    assert oa.lsig.logic.raw_binary is None

    ac = ApplicationClient(
        client=get_algod_client(), app=oa, signer=get_accounts().pop().signer
    )

    assert ac.approval_binary

    assert oa.child.approval.raw_binary is not None
    assert oa.child.clear.raw_binary is not None
    assert oa.lsig.logic.raw_binary is not None

    assert len(oa.lsig.logic._template_values) == 1


def test_build_recursive():
    app = OuterApp()
    pc = AppPrecompile(app)
    pc.compile(get_algod_client())
    _check_app_precompiles(pc)


class LargeApp(Application):
    longBytes = 4092 * b"A"
    longBytes2 = 2048 * b"A"

    @external
    def compare_big_byte_strings(self):
        return pt.Assert(pt.Bytes(self.longBytes) != pt.Bytes(self.longBytes2))


def test_large_app_create():
    class LargeAppDeployer(Application):
        large_app = AppPrecompile(LargeApp())

        @external
        def deploy_large_app(self, *, output: pt.abi.Uint64):
            return pt.Seq(
                pt.InnerTxnBuilder.Execute(self.large_app.get_create_config()),
                output.set(pt.InnerTxn.application_id()),
            )

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), LargeAppDeployer(), signer=acct.signer)

    ac.create()
    ac.fund(1_000_000)
    result = ac.call(LargeAppDeployer.deploy_large_app)
    print(result.return_value)


def test_page_hash():
    class SmallApp(Application):
        pass

    small_precompile = AppPrecompile(SmallApp())
    small_precompile.compile(get_algod_client())
    _check_app_precompiles(small_precompile)


def test_extra_page_population():

    app = LargeApp()
    app_precompile = AppPrecompile(app)
    app_precompile.compile(get_algod_client())
    _check_app_precompiles(app_precompile)

    assert app_precompile.approval.program_pages is not None
    assert app_precompile.clear.program_pages is not None
    recovered_approval_binary = b""
    for approval_page in app_precompile.approval.program_pages:
        recovered_approval_binary += bytes.fromhex(approval_page.byte_str)

    recovered_clear_binary = b""
    for clear_page in app_precompile.clear.program_pages:
        recovered_clear_binary += bytes.fromhex(clear_page.byte_str)

    assert recovered_approval_binary == app_precompile.approval.raw_binary
    assert recovered_clear_binary == app_precompile.clear.raw_binary


def _check_app_precompiles(app_precompile: AppPrecompile):
    for _, p in app_precompile.app.precompiles.items():
        match p:
            case LSigPrecompile():
                _check_lsig_precompiles(p)
            case AppPrecompile():
                _check_app_precompiles(p)

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
