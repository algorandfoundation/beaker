from collections.abc import Callable

import pyteal as pt
import pytest
from Cryptodome.Hash import SHA512
from pyteal.ast.abi import AssetTransferTransaction, PaymentTransaction

from beaker import (
    Application,
    BuildOptions,
    GlobalStateBlob,
    GlobalStateValue,
    LocalStateBlob,
    LocalStateValue,
    ReservedGlobalStateValue,
    ReservedLocalStateValue,
    unconditional_create_approval,
)
from beaker.application_specification import ApplicationSpecification
from beaker.lib.storage import BoxList
from tests.conftest import check_application_artifacts_output_stability


def test_empty_application() -> None:
    app = Application("EmptyApp")
    check_application_artifacts_output_stability(app)


def test_unconditional_create_approval() -> None:
    app = Application("OnlyCreate").apply(unconditional_create_approval)
    check_application_artifacts_output_stability(app)


def test_avm_version() -> None:
    app = Application("EmptyAppVersion7", build_options=BuildOptions(avm_version=7))
    check_application_artifacts_output_stability(app)


def test_single_external() -> None:
    app = Application("SingleExternal")

    @app.external
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    check_application_artifacts_output_stability(app)


def test_internal_abi_subroutine_not_exposed() -> None:
    app = Application("InternalABISubroutine")

    @pt.ABIReturnSubroutine
    def do_permissioned_thing(*, output: pt.abi.Bool) -> pt.Expr:
        return pt.Seq((b := pt.abi.Bool()).set(pt.Int(1)), output.set(b))

    @app.external
    def doit(*, output: pt.abi.Bool) -> pt.Expr:
        return output.set(do_permissioned_thing())

    check_application_artifacts_output_stability(app)


def test_method_overload() -> None:
    app = Application("MethodOverload")

    @app.external(name="handle")
    def handle_algo(txn: PaymentTransaction) -> pt.Expr:
        return pt.Approve()

    @app.external(name="handle")
    def handle_asa(txn: AssetTransferTransaction) -> pt.Expr:
        return pt.Approve()

    assert {x.method for x in app.abi_externals.values()} == {handle_algo, handle_asa}
    compiled = app.build()
    assert compiled.contract
    assert isinstance(handle_algo, pt.ABIReturnSubroutine)
    assert isinstance(handle_asa, pt.ABIReturnSubroutine)
    assert compiled.contract.methods == [
        handle_algo.method_spec(),
        handle_asa.method_spec(),
    ]

    check_application_artifacts_output_stability(app)


def test_bare() -> None:
    app = Application("Bare")

    @app.create
    def create() -> pt.Expr:
        return pt.Approve()

    @app.update
    def update() -> pt.Expr:
        return pt.Approve()

    @app.delete
    def delete() -> pt.Expr:
        return pt.Approve()

    assert len(app.bare_actions) == 3, "Expected 3 bare externals: create,update,delete"


def test_mixed_bares() -> None:
    app = Application("MixedBares")

    @app.create
    def create() -> pt.Expr:
        return pt.Approve()

    @app.opt_in
    def opt_in(s: pt.abi.String) -> pt.Expr:
        return pt.Assert(pt.Len(s.get()))

    assert len(app.bare_actions) == 1
    assert len(app.abi_externals) == 1


def test_application_external_override_true() -> None:
    app = Application("ExternalOverride")

    @app.external()
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    @app.external(override=True, name="handle")
    def handle_2() -> pt.Expr:
        return pt.Assert(pt.Int(2))

    compiled = app.build()
    assert compiled.contract

    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert list(app.abi_externals) == ["handle()void"]
    assert (
        compiled.contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"


def test_application_external_override_false() -> None:
    app = Application("ExternalOverrideFalse")

    @app.external
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    with pytest.raises(ValueError):

        @app.external(override=False, name="handle")
        def handle_2() -> pt.Expr:
            return pt.Assert(pt.Int(2))


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_external_override_none(
    create_existing_handle: bool,  # noqa: FBT001
) -> None:
    app = Application(
        f"ExternalOverrideNone{'With' if create_existing_handle else 'Without'}Existing"
    )

    if create_existing_handle:

        @app.external
        def handle() -> pt.Expr:
            return pt.Assert(pt.Int(1))

    @app.external(override=None, name="handle")
    def handle_2() -> pt.Expr:
        return pt.Assert(pt.Int(2))

    contract = app.build().contract
    assert contract
    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert (
        contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"
    assert list(app.abi_externals) == ["handle()void"]


def test_application_bare_override_true() -> None:
    app = Application("BareOverrideTrue")

    @app.external(bare=True, method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    @app.external(
        bare=True,
        method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL),
        override=True,
        name="handle",
    )
    def handle_2() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    app.build()
    assert list(app.bare_actions) == ["opt_in"]


def test_application_bare_override_false() -> None:
    app = Application("BareOverrideFalse")

    @app.external(bare=True, method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    with pytest.raises(ValueError):

        @app.external(
            bare=True,
            method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL),
            override=False,
            name="handle",
        )
        def handle_2() -> pt.Expr:
            return pt.Assert(pt.Int(1))


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_bare_override_none(
    create_existing_handle: bool,  # noqa: FBT001
) -> None:
    app = Application(
        f"BareOverrideNone{'With' if create_existing_handle else 'Without'}Existing"
    )

    if create_existing_handle:

        @app.external(
            bare=True, method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL)
        )
        def handle() -> pt.Expr:
            return pt.Assert(pt.Int(1))

    @app.external(
        bare=True,
        method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL),
        override=None,
        name="handle",
    )
    def handle_2() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    app.build()
    assert list(app.bare_actions) == ["opt_in"]


def test_state_init() -> None:
    from pyteal import abi

    class MyState:
        # global
        blob = GlobalStateBlob(keys=4, descr="blob_description")
        byte_val = GlobalStateValue(
            stack_type=pt.TealType.bytes, descr="byte_val_description"
        )
        uint_val = GlobalStateValue(
            stack_type=pt.TealType.uint64, descr="uint_val_description"
        )
        byte_dynamic = ReservedGlobalStateValue(
            stack_type=pt.TealType.bytes, max_keys=3, descr="byte_dynamic_description"
        )
        uint_dynamic = ReservedGlobalStateValue(
            stack_type=pt.TealType.uint64, max_keys=3, descr="uint_dynamic_description"
        )
        # local
        local_blob = LocalStateBlob(keys=3, descr="local_blob_description")
        byte_local_val = LocalStateValue(
            stack_type=pt.TealType.bytes, descr="byte_local_val_description"
        )
        uint_local_val = LocalStateValue(
            stack_type=pt.TealType.uint64, descr="uint_local_val_description"
        )
        byte_local_dynamic = ReservedLocalStateValue(
            stack_type=pt.TealType.bytes,
            max_keys=2,
            descr="byte_local_dynamic_description",
        )
        uint_local_dynamic = ReservedLocalStateValue(
            stack_type=pt.TealType.uint64,
            max_keys=2,
            descr="uint_local_dynamic_description",
        )
        # box
        lst = BoxList(value_type=abi.Uint32, elements=5, name="lst_description")
        # not-state
        not_a_state_var = pt.Int(1)

    app = Application("TestStateInit", state=MyState()).apply(
        unconditional_create_approval, initialize_global_state=True
    )

    @app.opt_in(allow_create=True)
    def opt_in() -> pt.Expr:
        return pt.Seq(
            pt.If(
                pt.Txn.application_id() == pt.Int(0),
                app.initialize_global_state(),
            ),
            app.initialize_local_state(),
        )

    check_application_artifacts_output_stability(app)


def test_default_param_state() -> None:
    class HintyState:
        asset_id = GlobalStateValue(pt.TealType.uint64, default=pt.Int(123))

    h = Application("Hinty", state=HintyState())

    @h.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = HintyState.asset_id,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Assert(aid.asset_id() == HintyState.asset_id)

    hints = h.build().hints
    sig = hintymeth.method_signature()
    assert sig in hints, "Expected a hint available for the method"

    hint = hints[sig]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default["source"] == "global-state"
    assert (
        default["data"] == HintyState.asset_id.str_key()
    ), "Expected the hint to match the method spec"


#
#
def test_default_param_const() -> None:
    const_val = 123

    app = Application("ParamDefaultConst")

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = const_val,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    hints = app.build().hints
    sig = hintymeth.method_signature()
    assert sig in hints, "Expected a hint available for the method"

    hint = hints[sig]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default["source"] == "constant"
    assert default["data"] == const_val, "Expected the hint to match the method spec"


def test_default_read_only_method() -> None:
    const_val = 123

    app = Application("ParamDefaultMethodDryRun")

    @app.external(read_only=True)
    def get_asset_id(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(pt.Int(const_val))

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = get_asset_id,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    hints = app.build().hints
    sig = hintymeth.method_signature()
    assert sig in hints, "Expected a hint available for the method"

    hint = hints[sig]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert isinstance(get_asset_id, pt.ABIReturnSubroutine)
    assert default["source"] == "abi-method"
    assert (
        default["data"] == get_asset_id.method_spec().dictify()
    ), "Expected the hint to match the method spec"


def _get_full_app_spec() -> Application:
    class SpecdState:
        decl_global_val = GlobalStateValue(pt.TealType.uint64)
        decl_local_val = LocalStateValue(pt.TealType.uint64)

    app = Application("Specd", state=SpecdState())

    @app.external(read_only=True)
    def get_asset_id(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(pt.Int(123))

    @app.external
    def annotated_meth(
        aid: pt.abi.Asset = get_asset_id,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Assert(pt.Int(1))

    class Thing(pt.abi.NamedTuple):
        a: pt.abi.Field[pt.abi.Uint64]
        b: pt.abi.Field[pt.abi.Uint32]

    @app.external
    def struct_meth(thing: Thing) -> pt.Expr:
        return pt.Approve()

    @app.external
    def default_global_state(
        value: pt.abi.Uint64 = SpecdState.decl_global_val,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Approve()

    return app


def _get_partial_app_spec() -> Application:
    class SpecdState:
        decl_global_val = GlobalStateValue(pt.TealType.uint64)
        decl_local_val = LocalStateValue(pt.TealType.uint64)

    app = Application("PartialSpec", state=SpecdState())

    class Thing(pt.abi.NamedTuple):
        a: pt.abi.Field[pt.abi.Uint64]
        b: pt.abi.Field[pt.abi.Uint32]

    @app.external
    def struct_meth(thing: Thing) -> pt.Expr:
        return pt.Approve()

    @app.external
    def default_global_state(
        value: pt.abi.Uint64 = SpecdState.decl_global_val,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Approve()

    return app


def _get_minimal_app_spec() -> Application:
    app = Application("MinimalSpec")

    return app


@pytest.mark.parametrize(
    "app_factory", [_get_full_app_spec, _get_partial_app_spec, _get_minimal_app_spec]
)
def test_app_spec(app_factory: Callable[[], Application]) -> None:
    """Test various application.json (aka app spec) outputs with an approval test"""
    app = app_factory()
    check_application_artifacts_output_stability(app)


@pytest.mark.parametrize(
    "app_factory", [_get_full_app_spec, _get_partial_app_spec, _get_minimal_app_spec]
)
def test_app_spec_from_json(app_factory: Callable[[], Application]) -> None:
    app = app_factory()
    app_spec1 = app.build()

    json = app_spec1.to_json()
    app_spec2 = ApplicationSpecification.from_json(json)

    assert app_spec1 == app_spec2


def test_struct_args() -> None:
    from algosdk.abi import Argument, Method, Returns

    class UserRecord(pt.abi.NamedTuple):
        addr: pt.abi.Field[pt.abi.Address]
        balance: pt.abi.Field[pt.abi.Uint64]
        nickname: pt.abi.Field[pt.abi.String]

    app = Application("StructArgs")

    @app.external
    def structy(user_record: UserRecord) -> pt.Expr:
        return pt.Assert(pt.Int(1))

    arg = Argument("(address,uint64,string)", name="user_record")
    ret = Returns("void")
    assert Method("structy", [arg], ret) == structy.method_spec()

    assert app.build().hints[structy.method_signature()].structs == {
        "user_record": {
            "name": "UserRecord",
            "elements": [
                ["addr", "address"],
                ["balance", "uint64"],
                ["nickname", "string"],
            ],
        }
    }


def test_closure_vars() -> None:
    def make_app(value: str) -> Application:
        app = Application("InAClosure")

        v = pt.Bytes(value)

        @app.external
        def use_it() -> pt.Expr:
            return pt.Log(v)

        @app.external
        def call_it() -> pt.Expr:
            return use_it_internal()

        @pt.Subroutine(pt.TealType.none)
        def use_it_internal() -> pt.Expr:
            return pt.Log(v)

        return app

    i1 = make_app("first")
    i1_approval_program = i1.build().approval_program
    assert i1_approval_program

    i2 = make_app("second")
    i2_approval_program = i2.build().approval_program
    assert i2_approval_program

    assert "first" in i1_approval_program, "Expected to see the string `first`"
    assert "second" in i2_approval_program, "Expected to see the string `second`"

    assert "second" not in i1_approval_program
    assert "first" not in i2_approval_program


def hashy(sig: str) -> bytes:
    chksum = SHA512.new(truncate="256")
    chksum.update(sig.encode())
    return chksum.digest()[:4]


def test_abi_method_details() -> None:
    app = Application("ABIApp")

    @app.external
    def meth() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    expected_sig = "meth()void"
    expected_selector = hashy(expected_sig)

    method_spec = meth.method_spec()
    assert method_spec.get_signature() == expected_sig
    assert method_spec.get_selector() == expected_selector


def test_multi_optin() -> None:
    test = Application("MultiOptIn")

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt1(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64) -> pt.Expr:
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt2(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64) -> pt.Expr:
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    test.build()
