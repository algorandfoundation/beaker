from typing import Any

import pyteal as pt
import pytest
from algosdk.constants import APP_PAGE_MAX_SIZE

from beaker import (
    Application,
    BuildOptions,
    GlobalStateValue,
    LocalStateValue,
    LogicSignature,
    LogicSignatureTemplate,
    consts,
    precompiled,
)
from beaker.client import ApplicationClient
from beaker.precompile import (
    PrecompileContextError,
    PrecompiledApplication,
    PrecompiledLogicSignature,
    PrecompiledLogicSignatureTemplate,
    _py_encode_uvarint,
)
from beaker.sandbox import get_accounts, get_algod_client

from tests.conftest import check_application_artifacts_output_stability


def test_compile() -> None:
    version = 8
    app = Application("test_compile", build_options=BuildOptions(avm_version=version))
    client = get_algod_client()
    precompile = PrecompiledApplication(app, client)

    assert precompile.approval_program
    approval_program = precompile.approval_program.raw_binary
    approval_map = precompile.approval_program.source_map

    assert len(approval_program) > 0, "Should have a valid approval program"
    assert approval_program[0] == version, "First byte should be the version we set"
    assert (
        approval_map and approval_map.version == 3
    ), "Should have valid source map with version 3"
    assert len(approval_map.pc_to_line) > 0, "Should have valid mapping"

    assert precompile.clear_program
    clear_program = precompile.clear_program.raw_binary
    clear_map = precompile.clear_program.source_map
    assert len(clear_program) > 0, "Should have a valid clear program"
    assert clear_program[0] == version, "First byte should be the version we set"
    assert (
        clear_map and clear_map.version == 3
    ), "Should have valid source map with version 3"
    assert len(clear_map.pc_to_line) > 0, "Should have valid mapping"


def test_precompile_basic() -> None:
    app = Application("BasicPrecompile")

    lsig = LogicSignature(
        pt.Seq(pt.Assert(pt.Int(1)), pt.Int(1)),
        build_options=BuildOptions(avm_version=6),
    )

    @app.external
    def check_it() -> pt.Expr:
        lsig_pc = precompiled(lsig)
        return pt.Assert(pt.Txn.sender() == lsig_pc.address())

    assert app._precompiled_lsigs == {}

    compiled = app.build(get_algod_client())

    assert compiled.approval_program
    assert compiled.clear_program
    lsig_pc = app._precompiled_lsigs.get(lsig)
    assert lsig_pc is not None
    assert lsig_pc.logic_program.binary is not None


TMPL_BYTE_VALS = [
    ("abc"),
    ("asdfasdfasdf"),
    (bytes(100)),
    ("的的的的的的的"),
]


@pytest.mark.parametrize("tmpl_val", TMPL_BYTE_VALS)
def test_templated_bytes(tmpl_val: str) -> None:
    app = Application("App")
    lsig = LogicSignatureTemplate(
        lambda tv: pt.Seq(pt.Assert(pt.Len(tv)), pt.Int(1)),
        runtime_template_variables={"tv": pt.TealType.bytes},
        build_options=BuildOptions(avm_version=6),
    )

    @app.external
    def check_it() -> pt.Expr:
        return pt.Assert(
            pt.Txn.sender() == app.precompiled(lsig).address(tv=pt.Bytes(tmpl_val))
        )

    assert app._precompiled_lsig_templates == {}

    compiled = app.build(get_algod_client())

    assert compiled.approval_program
    assert compiled.approval_program
    pc = app._precompiled_lsig_templates.get(lsig)
    assert pc is not None
    assert pc.logic_program.binary_hash is not None

    populated_teal = pc.populate_template(tv=tmpl_val)

    vlen = len(tmpl_val)
    if type(tmpl_val) is str:
        vlen = len(tmpl_val.encode("utf-8"))

    assert len(populated_teal) == len(pc.logic_program.raw_binary) + vlen + (
        len(_py_encode_uvarint(vlen)) - 1
    )


TMPL_INT_VALS = [(10), (1000), (int(2.9e9))]


@pytest.mark.parametrize("tmpl_val", TMPL_INT_VALS)
def test_templated_ints(tmpl_val: int) -> None:
    app = Application("App")
    lsig = LogicSignatureTemplate(
        lambda tv: pt.Seq(pt.Assert(tv), pt.Int(1)),
        runtime_template_variables={"tv": pt.TealType.uint64},
        build_options=BuildOptions(avm_version=6),
    )

    @app.external
    def check_it() -> pt.Expr:
        lsig_pc = precompiled(lsig)
        return pt.Assert(pt.Txn.sender() == lsig_pc.address(tv=pt.Int(tmpl_val)))

    assert app._precompiled_lsig_templates == {}

    compiled = app.build(get_algod_client())

    assert compiled.approval_program
    assert compiled.clear_program
    pc = app._precompiled_lsig_templates.get(lsig)
    assert pc is not None
    assert pc.logic_program.binary_hash is not None

    populated_teal = pc.populate_template(tv=tmpl_val)

    assert len(populated_teal) == len(pc.logic_program.raw_binary) + (
        len(_py_encode_uvarint(tmpl_val)) - 1
    )


def make_app_with_precompiles() -> Application:
    inner_app = Application("InnerApp")
    inner_lsig = LogicSignatureTemplate(
        pt.Approve(),
        runtime_template_variables={"nonce": pt.TealType.bytes},
    )

    app = Application("OuterApp")

    @app.external
    def doit(nonce: pt.abi.DynamicBytes, *, output: pt.abi.Uint64) -> pt.Expr:
        child = precompiled(inner_app)
        lsig = precompiled(inner_lsig)
        return pt.Seq(
            pt.Assert(pt.Txn.sender() == lsig.address(nonce=nonce.get())),
            pt.InnerTxnBuilder.Execute(
                {
                    pt.TxnField.type_enum: pt.TxnType.ApplicationCall,
                    pt.TxnField.approval_program: child.approval_program.binary,
                    pt.TxnField.clear_state_program: child.clear_program.binary,
                    pt.TxnField.fee: pt.Int(0),
                }
            ),
            output.set(pt.InnerTxn.created_application_id()),
        )

    return app


def test_nested_precompile() -> None:
    oa = make_app_with_precompiles()

    # Nothing is available until we build out the app and all its precompiles
    assert oa._precompiled_apps == {}
    assert oa._precompiled_lsigs == {}
    assert oa._precompiled_lsig_templates == {}

    precompile = PrecompiledApplication(oa, get_algod_client())

    assert precompile.approval_program.raw_binary

    (child,) = oa._precompiled_apps.values()
    assert child is not None
    (lsig,) = oa._precompiled_lsig_templates.values()
    assert lsig is not None

    assert child.approval_program.raw_binary is not None
    assert child.clear_program.raw_binary is not None
    assert lsig.logic_program.raw_binary is not None

    assert len(lsig._template_values) == 1


def test_build_recursive() -> None:
    app = make_app_with_precompiles()
    client = get_algod_client()
    pc = PrecompiledApplication(app, client)
    _check_app_precompiles(app, pc)


def make_large_app() -> Application:
    app = Application(name="LargeApp")

    @app.external
    def compare_big_byte_strings() -> pt.Expr:
        return pt.Assert(pt.Bytes(4092 * b"A") != pt.Bytes(2048 * b"A"))

    return app


def test_large_app_create() -> None:
    la = make_large_app()

    deployer = Application("LargeAppDeployer")

    @deployer.external
    def deploy_large_app(*, output: pt.abi.Uint64) -> pt.Expr:
        large_app = precompiled(la)
        return pt.Seq(
            pt.InnerTxnBuilder.Execute(large_app.get_create_config()),
            output.set(pt.InnerTxn.application_id()),
        )

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), deployer, signer=acct.signer)

    ac.create()
    ac.fund(1_000_000)
    result = ac.call(deploy_large_app)
    assert result.return_value >= 0


def test_page_hash() -> None:
    app = Application("SmallApp")
    small_precompile = PrecompiledApplication(app, get_algod_client())
    _check_app_precompiles(app, small_precompile)


def test_extra_page_population() -> None:

    app = make_large_app()
    app_precompile = PrecompiledApplication(app, get_algod_client())
    _check_app_precompiles(app, app_precompile)

    assert app_precompile.approval_program.pages is not None
    assert app_precompile.clear_program.pages is not None
    recovered_approval_binary = b""
    for approval_page in app_precompile.approval_program.pages:
        assert isinstance(approval_page, pt.Bytes)
        recovered_approval_binary += bytes.fromhex(approval_page.byte_str)

    recovered_clear_binary = b""
    for clear_page in app_precompile.clear_program.pages:
        assert isinstance(clear_page, pt.Bytes)
        recovered_clear_binary += bytes.fromhex(clear_page.byte_str)

    assert recovered_approval_binary == app_precompile.approval_program.raw_binary
    assert recovered_clear_binary == app_precompile.clear_program.raw_binary


def _check_app_precompiles(
    app: Application, app_precompile: PrecompiledApplication
) -> None:
    for lp in app._precompiled_lsigs.values():
        _check_lsig_precompiles(lp)
    for nested_app, app_pc in app._precompiled_apps.items():
        _check_app_precompiles(nested_app, app_pc)
    for lsig_template, ltp in app._precompiled_lsig_templates.items():
        _check_lsig_template_precompiles(lsig_template, ltp)

    assert app_precompile.approval_program.teal != ""
    assert app_precompile.approval_program.raw_binary is not None
    assert app_precompile.approval_program.binary.byte_str != ""
    assert app_precompile.approval_program.source_map is not None
    assert app_precompile.approval_program.binary_hash is not None

    assert len(app_precompile.approval_program.pages) > 0

    assert app_precompile.clear_program.teal != ""
    assert app_precompile.clear_program.raw_binary is not None
    assert app_precompile.clear_program.binary.byte_str != ""
    assert app_precompile.clear_program.source_map is not None
    assert app_precompile.clear_program.binary_hash is not None
    assert len(app_precompile.clear_program.pages) > 0


def _check_lsig_precompiles(lsig_precompile: PrecompiledLogicSignature) -> None:
    assert lsig_precompile.logic_program.teal != ""
    assert lsig_precompile.logic_program.raw_binary is not None
    assert lsig_precompile.logic_program.binary.byte_str != ""
    assert lsig_precompile.logic_program.source_map is not None
    assert lsig_precompile.logic_program.binary_hash is not None
    assert lsig_precompile.address()


def _check_lsig_template_precompiles(
    lsig_template: LogicSignatureTemplate,
    lsig_precompile: PrecompiledLogicSignatureTemplate,
) -> None:
    assert lsig_precompile.logic_program.teal != ""
    assert lsig_precompile.logic_program.raw_binary is not None
    assert lsig_precompile.logic_program.binary.byte_str != ""
    assert lsig_precompile.logic_program.source_map is not None
    assert lsig_precompile.logic_program.binary_hash is not None
    assert (
        lsig_precompile._template_values.keys()
        == lsig_template.runtime_template_variables.keys()
    )


def test_precompile_outside_function() -> None:
    app = Application("App")
    another_app = Application("AnotherApp")

    with pytest.raises(
        PrecompileContextError,
        match="precompiled must be called within a function used by an Application",
    ):
        precompiled(another_app)

    with pytest.raises(
        PrecompileContextError,
        match="precompiled must be called within a function used by an Application",
    ):
        app.precompiled(another_app)


def test_precompile_current_app() -> None:
    app = Application("App")

    @app.external
    def method() -> pt.Expr:
        precompiled(app)
        return pt.Approve()

    with pytest.raises(
        PrecompileContextError, match="Attempted to precompile current Application"
    ):
        app.build(client=get_algod_client())


def test_precompile_called_on_another_app() -> None:
    app = Application("App")
    another_app = Application("AnotherApp")

    @app.external
    def method() -> pt.Expr:
        another_app.precompiled(app)
        return pt.Approve()

    with pytest.raises(
        PrecompileContextError,
        match='Application.precompiled called for app "AnotherApp" inside of a function of app "App"',
    ):
        app.build(client=get_algod_client())


def test_precompile_without_client() -> None:
    app = Application("App")
    another_app = Application("AnotherApp")

    @app.external
    def method() -> pt.Expr:
        precompiled(another_app)
        return pt.Approve()

    with pytest.raises(
        PrecompileContextError,
        match="Precompilation requires use of a client when calling Application.build",
    ):
        app.build()


def test_precompile_bad_type() -> None:
    app = Application("App")

    @app.external
    def method() -> pt.Expr:
        precompiled(pt.ScratchVar())  # type: ignore[call-overload]
        return pt.Approve()

    with pytest.raises(
        TypeError,
        match="Expected an Application, LogicSignature, or LogicSignatureTemplate, but got a <class 'pyteal.ScratchVar'>",
    ):
        app.build(client=get_algod_client())


def test_precompile_in_subroutine() -> None:
    app_to_deploy = Application("InnerApp")

    @pt.Subroutine(pt.TealType.uint64)
    def deploy_app() -> pt.Expr:
        pc = precompiled(app_to_deploy)
        return pt.Seq(
            pt.InnerTxnBuilder.Execute(pc.get_create_config()),
            # return the app id of the newly created app
            pt.InnerTxn.created_application_id(),
        )

    app = Application("DeployInSubroutine")

    @app.external
    def deploy(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(deploy_app())

    check_application_artifacts_output_stability(app)


def test_precompile_get_create_config_single_page() -> None:
    large_app_one_page_each = Application("LargeAppOnePageEach")

    silly_expr = pt.Assert(pt.Bytes(b"A" * (APP_PAGE_MAX_SIZE // 2)) != pt.Bytes(b""))

    @large_app_one_page_each.external
    def foo() -> pt.Expr:
        return silly_expr

    @large_app_one_page_each.clear_state
    def bar() -> pt.Expr:
        return silly_expr

    deployer_app = Application("Deployer")

    @deployer_app.external
    def deploy(*, output: pt.abi.Uint64) -> pt.Expr:
        pc = precompiled(large_app_one_page_each)
        return pt.Seq(
            pt.InnerTxnBuilder.Execute(pc.get_create_config()),
            # return the app id of the newly created app
            output.set(pt.InnerTxn.created_application_id()),
        )

    acct, *_ = get_accounts()
    client = ApplicationClient(
        client=get_algod_client(), app=deployer_app, signer=acct.signer
    )
    app_id, *_ = client.create()
    assert app_id > 0
    client.fund(1 * consts.algo)
    result = client.call(deploy)
    assert result.return_value > app_id


def test_deploy_inner_app_state() -> None:
    class InnerAppState:
        uint_val = GlobalStateValue(pt.TealType.uint64, default=pt.Int(42))
        bytes_val = GlobalStateValue(pt.TealType.bytes, default=pt.Bytes(b"hello"))

        local_uint = LocalStateValue(pt.TealType.uint64, default=pt.Int(123))
        local_bytes = LocalStateValue(pt.TealType.bytes, default=pt.Bytes(b"goodbye"))

    inner_app = Application("InnerApp", state=InnerAppState())

    @inner_app.opt_in(bare=True, allow_create=True)
    def opt_in() -> pt.Expr:
        return pt.Seq(
            pt.If(
                pt.Txn.application_id() == pt.Int(0),
                inner_app.initialize_global_state(),
            ),
            inner_app.initialize_local_state(),
        )

    deployer = Application("Deployer")

    @deployer.external
    def deploy(*, output: pt.abi.Uint64) -> pt.Expr:
        pc = precompiled(inner_app)
        return pt.Seq(
            pt.InnerTxnBuilder.Execute(
                {
                    **pc.get_create_config(),
                    pt.TxnField.on_completion: pt.OnComplete.OptIn,
                }
            ),
            # return the app id of the newly created app
            output.set(pt.InnerTxn.created_application_id()),
        )

    acct, *_ = get_accounts()
    client = ApplicationClient(
        client=get_algod_client(), app=deployer, signer=acct.signer
    )
    client.create()
    client.fund(1 * consts.algo)
    result = client.call(deploy)
    inner_client = ApplicationClient(
        client=get_algod_client(),
        app=inner_app,
        app_id=result.return_value,
        signer=acct.signer,
    )
    assert inner_client.get_local_state(account=client.app_addr) == {
        "local_bytes": "goodbye",
        "local_uint": 123,
    }
    assert inner_client.get_global_state() == {"bytes_val": "hello", "uint_val": 42}


def test_lsig_template_with_bad_arg_name_set() -> None:
    lsig_tmpl = LogicSignatureTemplate(
        pt.Approve(), runtime_template_variables={"nonce": pt.TealType.uint64}
    )

    pc = PrecompiledLogicSignatureTemplate(lsig_tmpl, client=get_algod_client())

    f: Any
    for f in pc.populate_template, pc.address, pc.populate_template_expr:
        with pytest.raises(
            ValueError, match="Expected arguments named: nonce but got: "
        ):
            f()
        with pytest.raises(
            ValueError, match="Expected arguments named: nonce but got: nunce"
        ):
            f(nunce=1)
        with pytest.raises(
            ValueError, match="Expected arguments named: nonce but got: nonce, believe"
        ):
            f(nonce=1, believe=True)


def test_lsig_template_arg_type_checking_with_int() -> None:
    lsig_tmpl = LogicSignatureTemplate(
        pt.Approve(), runtime_template_variables={"nonce": pt.TealType.uint64}
    )

    pc = PrecompiledLogicSignatureTemplate(lsig_tmpl, client=get_algod_client())

    with pytest.raises(pt.TealTypeError):
        pc.address(nonce=pt.Bytes(b"1"))
    with pytest.raises(pt.TealTypeError):
        pc.populate_template_expr(nonce=pt.Bytes(b"1"))
    with pytest.raises(pt.TealTypeError):
        pc.populate_template(nonce=b"1")

    pc.address(nonce=pt.Int(1))
    pc.populate_template_expr(nonce=pt.Int(1))
    pc.populate_template(nonce=1)


def test_lsig_template_arg_type_checking_with_bytes() -> None:
    lsig_tmpl = LogicSignatureTemplate(
        pt.Approve(), runtime_template_variables={"nonce": pt.TealType.bytes}
    )

    pc = PrecompiledLogicSignatureTemplate(lsig_tmpl, client=get_algod_client())

    with pytest.raises(pt.TealTypeError):
        pc.address(nonce=pt.Int(1))
    with pytest.raises(pt.TealTypeError):
        pc.populate_template_expr(nonce=pt.Int(1))
    with pytest.raises(pt.TealTypeError):
        pc.populate_template(nonce=1)

    pc.address(nonce=pt.Bytes(b"1"))
    pc.populate_template_expr(nonce=pt.Bytes(b"1"))
    pc.populate_template(nonce=b"1")
