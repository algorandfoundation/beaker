import pyteal as pt
import pytest
from Cryptodome.Hash import SHA512
from pyteal.ast.abi import PaymentTransaction, AssetTransferTransaction

from beaker import ApplicationStateBlob, AccountStateBlob
from beaker.application import (
    Application,
    CompilerOptions,
    MethodConfig,
    this_app,
)
from beaker.blueprints import unconditional_create_approval
from beaker.decorators import DefaultArgumentClass
from beaker.lib.storage import List
from beaker.state import (
    ReservedApplicationStateValue,
    ApplicationStateValue,
    AccountStateValue,
    ReservedAccountStateValue,
)
from tests.conftest import check_application_artifacts_output_stability

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_empty_application():
    app = Application("EmptyApp")
    check_application_artifacts_output_stability(app)


def test_unconditional_create_approval():
    app = Application("OnlyCreate").implement(unconditional_create_approval)
    check_application_artifacts_output_stability(app)


def test_avm_version():
    app = Application(
        "EmptyAppVersion7", compiler_options=CompilerOptions(avm_version=7)
    )
    check_application_artifacts_output_stability(app)


def test_single_external():
    app = Application("SingleExternal")

    @app.external
    def handle() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    check_application_artifacts_output_stability(app)


def test_internal_abi_subroutine_not_exposed():
    app = Application("InternalABISubroutine")

    @pt.ABIReturnSubroutine
    def do_permissioned_thing(*, output: pt.abi.Bool) -> pt.Expr:
        return pt.Seq((b := pt.abi.Bool()).set(pt.Int(1)), output.set(b))

    @app.external
    def doit(*, output: pt.abi.Bool) -> pt.Expr:
        return output.set(do_permissioned_thing())

    check_application_artifacts_output_stability(app)


def test_method_overload():
    app = Application("MethodOverload")

    @app.external(name="handle")
    def handle_algo(txn: PaymentTransaction) -> pt.Expr:
        return pt.Approve()

    @app.external(name="handle")
    def handle_asa(txn: AssetTransferTransaction) -> pt.Expr:
        return pt.Approve()

    assert app.abi_methods == {"handle_algo": handle_algo, "handle_asa": handle_asa}
    compiled = app.compile()
    assert compiled.contract
    assert isinstance(handle_algo, pt.ABIReturnSubroutine)
    assert isinstance(handle_asa, pt.ABIReturnSubroutine)
    assert compiled.contract.methods == [
        handle_algo.method_spec(),
        handle_asa.method_spec(),
    ]

    check_application_artifacts_output_stability(app)


def test_bare():
    app = Application("Bare")

    @app.create(bare=True)
    def create() -> pt.Expr:
        return pt.Approve()

    @app.update(bare=True)
    def update() -> pt.Expr:
        return pt.Approve()

    @app.delete(bare=True)
    def delete() -> pt.Expr:
        return pt.Approve()

    assert len(app.bare_methods) == 3, "Expected 3 bare externals: create,update,delete"


def test_mixed_bares():
    app = Application("MixedBares")

    @app.create(bare=True)
    def create():
        return pt.Approve()

    @app.opt_in
    def opt_in(s: pt.abi.String):
        return pt.Assert(pt.Len(s.get()))

    assert len(app.bare_methods) == 1
    assert len(app.abi_methods) == 1


# TODO: add tests for CallConfig parameter in decorators


def test_application_external_override_true():
    app = Application("ExternalOverride")

    @app.external()
    def handle():
        return pt.Assert(pt.Int(1))

    @app.external(override=True, name="handle")
    def handle_2():
        return pt.Assert(pt.Int(2))

    compiled = app.compile()
    assert compiled.contract

    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert list(app.abi_methods) == ["handle_2"]
    assert (
        compiled.contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"


def test_application_external_override_false():
    app = Application("ExternalOverrideFalse")

    @app.external
    def handle():
        return pt.Assert(pt.Int(1))

    with pytest.raises(ValueError):

        @app.external(override=False, name="handle")
        def handle_2():
            return pt.Assert(pt.Int(2))


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_external_override_none(create_existing_handle: bool):
    app = Application(
        f"ExternalOverrideNone{'With' if create_existing_handle else 'Without'}Existing"
    )

    if create_existing_handle:

        @app.external
        def handle():
            return pt.Assert(pt.Int(1))

    @app.external(override=None, name="handle")
    def handle_2():
        return pt.Assert(pt.Int(2))

    contract = app.compile().contract
    assert contract
    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert (
        contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"
    assert list(app.abi_methods) == ["handle_2"]


def test_application_bare_override_true():
    app = Application("BareOverrideTrue")

    @app.external(bare=True, method_config=MethodConfig(opt_in=pt.CallConfig.CALL))
    def handle():
        return pt.Assert(pt.Int(1))

    @app.external(
        bare=True,
        method_config=MethodConfig(opt_in=pt.CallConfig.CALL),
        override=True,
        name="handle",
    )
    def handle_2():
        return pt.Assert(pt.Int(1))

    app.compile()
    assert list(app.bare_methods) == ["handle_2"]


def test_application_bare_override_false():
    app = Application("BareOverrideFalse")

    @app.external(bare=True, method_config=MethodConfig(opt_in=pt.CallConfig.CALL))
    def handle():
        return pt.Assert(pt.Int(1))

    with pytest.raises(ValueError):

        @app.external(
            bare=True,
            method_config=MethodConfig(opt_in=pt.CallConfig.CALL),
            override=False,
            name="handle",
        )
        def handle_2():
            return pt.Assert(pt.Int(1))


# TODO: test clear_state


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_bare_override_none(create_existing_handle: bool):
    app = Application(
        f"BareOverrideNone{'With' if create_existing_handle else 'Without'}Existing"
    )

    if create_existing_handle:

        @app.external(bare=True, method_config=MethodConfig(opt_in=pt.CallConfig.CALL))
        def handle():
            return pt.Assert(pt.Int(1))

    @app.external(
        bare=True,
        method_config=MethodConfig(opt_in=pt.CallConfig.CALL),
        override=None,
        name="handle",
    )
    def handle_2():
        return pt.Assert(pt.Int(1))

    app.compile()
    assert list(app.bare_methods) == ["handle_2"]


def test_state_init():
    from pyteal import abi

    class MyState:
        # global
        blob = ApplicationStateBlob(keys=4, descr="blob_description")
        byte_val = ApplicationStateValue(
            stack_type=pt.TealType.bytes, descr="byte_val_description"
        )
        uint_val = ApplicationStateValue(
            stack_type=pt.TealType.uint64, descr="uint_val_description"
        )
        byte_dynamic = ReservedApplicationStateValue(
            stack_type=pt.TealType.bytes, max_keys=3, descr="byte_dynamic_description"
        )
        uint_dynamic = ReservedApplicationStateValue(
            stack_type=pt.TealType.uint64, max_keys=3, descr="uint_dynamic_description"
        )
        # local
        acct_blob = AccountStateBlob(keys=3, descr="acct_blob_description")
        byte_acct_val = AccountStateValue(
            stack_type=pt.TealType.bytes, descr="byte_acct_val_description"
        )
        uint_acct_val = AccountStateValue(
            stack_type=pt.TealType.uint64, descr="uint_acct_val_description"
        )
        byte_acct_dynamic = ReservedAccountStateValue(
            stack_type=pt.TealType.bytes,
            max_keys=2,
            descr="byte_acct_dynamic_description",
        )
        uint_acct_dynamic = ReservedAccountStateValue(
            stack_type=pt.TealType.uint64,
            max_keys=2,
            descr="uint_acct_dynamic_description",
        )
        # box
        lst = List(value_type=abi.Uint32, elements=5, name="lst_description")
        # not-state
        not_a_state_var = pt.Int(1)

    app = Application("TestStateInit", state=MyState)

    @app.create
    def create() -> pt.Expr:
        return this_app().initialize_application_state()

    @app.opt_in(allow_create=True)
    def opt_in() -> pt.Expr:
        return pt.Seq(
            pt.If(
                pt.Txn.application_id() == pt.Int(0),
                this_app().initialize_application_state(),
            ),
            this_app().initialize_account_state(),
        )

    assert app._app_state.schema.num_uints == 4
    assert app._app_state.schema.num_byte_slices == 8
    # assert app._app_state.fields.keys() == {
    #     "uint_val",
    #     "byte_val",
    #     "uint_dynamic",
    #     "byte_dynamic",
    #     "blob",
    # }

    assert app._acct_state.schema.num_uints == 3
    assert app._acct_state.schema.num_byte_slices == 6
    # assert app._acct_state.fields.keys() == {
    #     "uint_acct_val",
    #     "byte_acct_val",
    #     "uint_acct_dynamic",
    #     "byte_acct_dynamic",
    #     "acct_blob",
    # }

    check_application_artifacts_output_stability(app)


def test_default_param_state():
    class HintyState:
        asset_id = ApplicationStateValue(pt.TealType.uint64, default=pt.Int(123))

    h = Application("Hinty", state=HintyState)

    @h.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = HintyState.asset_id,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == HintyState.asset_id)

    hints = h.compile().hints
    assert "hintymeth" in hints, "Expected a hint available for the method"

    hint = hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default.resolvable_class == DefaultArgumentClass.GlobalState
    assert (
        default.resolve_hint() == HintyState.asset_id.str_key()
    ), "Expected the hint to match the method spec"


#
#
def test_default_param_const():
    const_val = 123

    app = Application("ParamDefaultConst")

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = const_val,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    hints = app.compile().hints
    assert "hintymeth" in hints, "Expected a hint available for the method"

    hint = hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default.resolvable_class == DefaultArgumentClass.Constant
    assert (
        default.resolve_hint() == const_val
    ), "Expected the hint to match the method spec"


def test_default_read_only_method():
    const_val = 123

    app = Application("ParamDefaultMethodDryRun")

    @app.external(read_only=True)
    def get_asset_id(*, output: pt.abi.Uint64):
        return output.set(pt.Int(const_val))

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = get_asset_id,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    hints = app.compile().hints
    assert "hintymeth" in hints, "Expected a hint available for the method"

    hint = hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert isinstance(get_asset_id, pt.ABIReturnSubroutine)
    assert default.resolvable_class == DefaultArgumentClass.ABIMethod
    assert (
        default.resolve_hint() == get_asset_id.method_spec().dictify()
    ), "Expected the hint to match the method spec"


def test_app_spec():
    """Test various application.json (aka app spec) outputs with an approval test"""

    class SpecdState:
        decl_app_val = ApplicationStateValue(pt.TealType.uint64)
        decl_acct_val = AccountStateValue(pt.TealType.uint64)

    app = Application("Specd", state=SpecdState)

    @app.external(read_only=True)
    def get_asset_id(*, output: pt.abi.Uint64):
        return output.set(pt.Int(123))

    @app.external
    def annotated_meth(
        aid: pt.abi.Asset = get_asset_id,  # type: ignore[assignment]
    ):
        return pt.Assert(pt.Int(1))

    class Thing(pt.abi.NamedTuple):
        a: pt.abi.Field[pt.abi.Uint64]
        b: pt.abi.Field[pt.abi.Uint32]

    @app.external
    def struct_meth(thing: Thing):
        return pt.Approve()

    @app.external
    def default_app_state(
        value: pt.abi.Uint64 = SpecdState.decl_app_val,  # type: ignore[assignment]
    ):
        return pt.Approve()

    check_application_artifacts_output_stability(app)


#
#
# EXPECTED_BARE_HANDLERS = [
#     "create",
# ]
#
#
def test_struct_args():
    from algosdk.abi import Method, Argument, Returns

    class UserRecord(pt.abi.NamedTuple):
        addr: pt.abi.Field[pt.abi.Address]
        balance: pt.abi.Field[pt.abi.Uint64]
        nickname: pt.abi.Field[pt.abi.String]

    app = Application("StructArgs")

    @app.external
    def structy(user_record: UserRecord):
        return pt.Assert(pt.Int(1))

    arg = Argument("(address,uint64,string)", name="user_record")
    ret = Returns("void")
    assert Method("structy", [arg], ret) == structy.method_spec()

    assert app.compile().hints["structy"].structs == {
        "user_record": {
            "name": "UserRecord",
            "elements": [
                ("addr", "address"),
                ("balance", "uint64"),
                ("nickname", "string"),
            ],
        }
    }


def test_closure_vars():
    def Inst(value: str) -> Application:
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

    i1 = Inst("first")
    i1_approval_program = i1.compile().approval_program
    assert i1_approval_program

    i2 = Inst("second")
    i2_approval_program = i2.compile().approval_program
    assert i2_approval_program

    assert "first" in i1_approval_program, "Expected to see the string `first`"
    assert "second" in i2_approval_program, "Expected to see the string `second`"

    assert "second" not in i1_approval_program
    assert "first" not in i2_approval_program


def hashy(sig: str):
    chksum = SHA512.new(truncate="256")
    chksum.update(sig.encode())
    return chksum.digest()[:4]


def test_abi_method_details():
    app = Application("ABIApp")

    @app.external
    def meth():
        return pt.Assert(pt.Int(1))

    expected_sig = "meth()void"
    expected_selector = hashy(expected_sig)

    method_spec = meth.method_spec()
    assert method_spec.get_signature() == expected_sig
    assert method_spec.get_selector() == expected_selector


def test_multi_optin():
    test = Application("MultiOptIn")

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt1(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64):
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt2(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64):
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    test.compile()
