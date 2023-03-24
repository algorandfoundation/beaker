import re
from collections.abc import Callable
from pathlib import Path

import pyteal as pt
import pytest
from _pytest.monkeypatch import MonkeyPatch
from algokit_utils import ApplicationSpecification
from pyteal.ast.abi import AssetTransferTransaction, PaymentTransaction
from typing_extensions import assert_type

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


def test_method_config_allow_everything() -> None:
    from beaker.application import MethodConfigDict

    app = Application("AllowEverything")

    actions: MethodConfigDict = {
        "no_op": pt.CallConfig.ALL,
        "opt_in": pt.CallConfig.ALL,
        "close_out": pt.CallConfig.ALL,
        "update_application": pt.CallConfig.ALL,
        "delete_application": pt.CallConfig.ALL,
    }

    @app.external(method_config=actions)
    def abi() -> pt.Expr:
        return pt.Approve()

    @app.external(bare=True, method_config=actions)
    def bare() -> pt.Expr:
        return pt.Approve()

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Approve()

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


def test_bare_true() -> None:
    app = Application("Bare")

    @app.create(bare=True)
    def create() -> pt.Expr:
        return pt.Approve()

    assert_type(create, pt.SubroutineFnWrapper)

    @app.update(bare=True)
    def update() -> pt.Expr:
        return pt.Approve()

    assert_type(update, pt.SubroutineFnWrapper)

    @app.delete(bare=True)
    def delete() -> pt.Expr:
        return pt.Approve()

    assert_type(delete, pt.SubroutineFnWrapper)

    assert len(app.bare_actions) == 3, "Expected 3 bare externals: create,update,delete"


def test_bare_default() -> None:
    app = Application("Bare")

    @app.create
    def create() -> pt.Expr:
        return pt.Approve()

    assert_type(create, pt.ABIReturnSubroutine)

    @app.update
    def update() -> pt.Expr:
        return pt.Approve()

    assert_type(update, pt.ABIReturnSubroutine)

    @app.delete
    def delete() -> pt.Expr:
        return pt.Approve()

    assert_type(delete, pt.ABIReturnSubroutine)

    assert len(app.bare_actions) == 0, "Expected no bare externals"
    assert len(app.abi_externals) == 3, "Expected 3 ABI externals"


def test_mixed_bares() -> None:
    app = Application("MixedBares")

    @app.create(bare=True)
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


def test_deregister_abi_by_signature() -> None:
    app = Application("")

    @app.external
    def handle(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(42)

    assert app.abi_externals
    app.deregister_abi_method("handle()uint64")
    assert not app.abi_externals


def test_deregister_abi_by_reference() -> None:
    app = Application("")

    @app.external
    def handle(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(42)

    assert app.abi_externals
    app.deregister_abi_method(handle)
    assert not app.abi_externals


def test_deregister_bare_by_action_name() -> None:
    app = Application("")

    @app.opt_in(bare=True)
    def opt_in() -> pt.Expr:
        return pt.Approve()

    assert app.bare_actions
    app.deregister_bare_method("opt_in")
    assert not app.bare_actions


def test_deregister_bare_by_reference() -> None:
    app = Application("")

    @app.opt_in(bare=True)
    def opt_in() -> pt.Expr:
        return pt.Approve()

    assert app.bare_actions
    app.deregister_bare_method(opt_in)
    assert not app.bare_actions


def test_deregister_clear_state_by_action_name() -> None:
    app = Application("")

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Approve()

    assert app._clear_state_method
    app.deregister_bare_method("clear_state")
    assert not app._clear_state_method


def test_deregister_clear_state_by_reference() -> None:
    app = Application("")

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Approve()

    assert app._clear_state_method
    app.deregister_bare_method(clear_state)
    assert not app._clear_state_method


def test_deregister_clear_state_not_found() -> None:
    app = Application("")

    with pytest.raises(KeyError):
        app.deregister_bare_method("clear_state")


def test_deregister_opt_in_not_found() -> None:
    app = Application("")

    with pytest.raises(KeyError):
        app.deregister_bare_method("opt_in")


def test_deregister_bare_method_not_found() -> None:
    @pt.Subroutine(pt.TealType.uint64)
    def foo() -> pt.Expr:
        return pt.Int(1)

    app = Application("")
    with pytest.raises(LookupError, match='Not a registered bare method: "foo"'):
        app.deregister_bare_method(foo)


def test_deregister_abi_method_not_found() -> None:
    @pt.ABIReturnSubroutine
    def foo(x: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(x.get())

    app = Application("")
    with pytest.raises(KeyError):
        app.deregister_abi_method(foo)

    with pytest.raises(KeyError):
        app.deregister_abi_method(foo.method_signature())


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
        lst = BoxList(value_type=pt.abi.Uint32, elements=5, name="lst_description")
        # not-state
        not_a_state_var = pt.Int(1)

    app = Application("TestStateInit", state=MyState()).apply(
        unconditional_create_approval, initialize_global_state=True
    )

    @app.opt_in(bare=True, allow_create=True)
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


def test_multi_optin() -> None:
    test = Application("MultiOptIn")

    @test.opt_in
    def opt1(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64) -> pt.Expr:
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    @test.opt_in
    def opt2(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64) -> pt.Expr:
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    check_application_artifacts_output_stability(test)


def test_bare_no_op_no_create() -> None:
    app = Application("")

    @app.no_op(bare=True)
    def method() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(
        Exception,
        match="either handle CallConfig.CREATE in the no_op bare method, or add an ABI method that handles create",
    ):
        app.build()


def test_initialise_another_apps_global_state() -> None:
    class State1:
        uint_val = GlobalStateValue(stack_type=pt.TealType.uint64)

    class State2:
        bytes_val = GlobalStateValue(stack_type=pt.TealType.bytes)

    app1 = Application("App1", state=State1())
    app2 = Application("App2", state=State2())

    @app2.create
    def create() -> pt.Expr:
        return app1.initialize_global_state()

    with pytest.warns(
        match="Accessing state of Application App1 during compilation of Application App2"
    ):
        app2.build()


def test_initialise_another_apps_local_state() -> None:
    class State1:
        uint_val = LocalStateValue(stack_type=pt.TealType.uint64)

    class State2:
        bytes_val = LocalStateValue(stack_type=pt.TealType.bytes)

    app1 = Application("App1", state=State1())
    app2 = Application("App2", state=State2())

    @app2.opt_in
    def opt_in() -> pt.Expr:
        return app1.initialize_local_state()

    with pytest.warns(
        match="Accessing state of Application App1 during compilation of Application App2"
    ):
        app2.build()


def test_default_arg_external_requires_read_only() -> None:
    app = Application("")

    @app.external
    def roll_dice(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(4)  # chosen by fair dice roll. guaranteed to be random

    with pytest.raises(
        ValueError,
        match="Only ABI methods with read_only=True should be used as default arguments to other ABI methods",
    ):

        @app.external
        def rng(
            seed: pt.abi.Uint64 = roll_dice,  # type: ignore[assignment]
            *,
            output: pt.abi.Uint64,
        ) -> pt.Expr:
            return output.set(seed.get())


def test_default_arg_external_only_allows_current_app() -> None:
    other_app = Application("Other")

    @other_app.external(read_only=True)
    def other_app_ro(*, output: pt.abi.String) -> pt.Expr:
        return output.set("other")

    app = Application("App")

    @app.external(read_only=True)
    def this_app_ro(*, output: pt.abi.String) -> pt.Expr:
        return output.set("self")

    with pytest.raises(KeyError, match=re.escape("other_app_ro()string")):

        @app.external
        def method(
            ident: pt.abi.String = other_app_ro,  # type: ignore[assignment]
            *,
            output: pt.abi.Uint64,
        ) -> pt.Expr:
            return output.set(ident.length())

    with pytest.raises(
        ValueError, match="Can not use another app's method as a default value"
    ):
        (external_ref,) = other_app.abi_externals.values()

        @app.external
        def sneaky_method(
            ident: pt.abi.String = external_ref,  # type: ignore[assignment]
            *,
            output: pt.abi.Uint64,
        ) -> pt.Expr:
            return output.set(ident.length())


def test_default_arg_unknown_type() -> None:
    app = Application("")

    with pytest.raises(
        TypeError,
        match="Unexpected type for a default argument to ABI method: <class 'float'>",
    ):

        @app.external
        def method(
            value: pt.abi.Uint64 = 123.456,  # type: ignore[assignment]
            *,
            output: pt.abi.Uint64,
        ) -> pt.Expr:
            return output.set(value.get())


def test_application_subclass_warning() -> None:
    with pytest.warns(
        DeprecationWarning,
        match=(
            "Subclassing beaker.Application is deprecated, "
            "please see the migration guide at: https://algorand-devrel.github.io/beaker/html/migration.html"
        ),
    ):

        class MyApp(Application):
            pass


def test_app_spec_export_defaults_to_cwd(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    app = Application("App")
    app_spec_output_path = tmp_path / "application.json"
    assert not app_spec_output_path.exists()
    with monkeypatch.context():
        monkeypatch.chdir(tmp_path)
        app.build().export()
    assert app_spec_output_path.is_file()


def test_app_state_variance() -> None:
    class BaseStateX:
        uint_val = GlobalStateValue(pt.TealType.uint64)

    def blueprint_x(x: Application[BaseStateX]) -> None:
        assert_type(x.state.uint_val, GlobalStateValue)

    class BaseStateY:
        bytes_val = LocalStateValue(pt.TealType.bytes)

    def blueprint_y(y: Application[BaseStateY]) -> None:
        assert_type(y.state.bytes_val, LocalStateValue)

    def blueprint_any_state(z: Application) -> None:
        assert z

    class MyState(BaseStateX, BaseStateY):
        blob = GlobalStateBlob(keys=1)

    app = (
        Application("App", state=MyState())
        .apply(blueprint_x)
        .apply(blueprint_y)
        .apply(blueprint_any_state)
    )
    assert_type(app, Application[MyState])
    assert_type(app.state.blob, GlobalStateBlob)
