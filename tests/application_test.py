from typing import Final

import pyteal as pt
import pytest
from Cryptodome.Hash import SHA512
from pyteal.ast.abi import PaymentTransaction, AssetTransferTransaction

from beaker.application import Application, CompileOptions, MethodConfig
from beaker.decorators import DefaultArgumentClass
from beaker.state import (
    ReservedApplicationStateValue,
    ApplicationStateValue,
    AccountStateValue,
    ReservedAccountStateValue,
)

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_empty_application():
    class EmptyApp(Application):
        pass

    ea = EmptyApp()
    ea.compile()

    assert (
        ea.contract and ea.contract.name == "EmptyApp"
    ), "Expected router name to match class"
    assert (
        ea.acct_state.num_uints
        + ea.acct_state.num_byte_slices
        + ea.app_state.num_uints
        + ea.app_state.num_byte_slices
        == 0
    ), "Expected no schema"

    assert len(ea.bare_methods) == len(
        EXPECTED_BARE_HANDLERS
    ), f"Expected {len(EXPECTED_BARE_HANDLERS)} bare handlers: {EXPECTED_BARE_HANDLERS}"

    assert ea.approval_program, "Expected approval program to be compiled to teal"
    assert ea.clear_program, "Expected clear program to be compiled to teal"
    assert len(ea.contract.methods) == 0, "Expected no methods in the contract"


def test_avm_version():
    class EmptyApp(Application):
        pass

    ea = EmptyApp(compile_options=CompileOptions(avm_version=8))
    ea.compile()

    assert ea.avm_version == 8, "Expected avm v8"
    assert (
        ea.approval_program
        and ea.approval_program.split("\n")[0] == "#pragma version 8"
    )


class NoCreateApp(Application):
    def __init__(self):
        super().__init__(implement_default_create=False)


def test_single_external():
    app = Application()

    @app.external
    def handle():
        return pt.Assert(pt.Int(1))

    app.compile()
    assert app.contract

    assert len(app.abi_methods) == 1, "Expected a single external"
    assert app.contract.get_method_by_name("handle") == (
        app.abi_methods["handle"].method_spec()
    ), "Expected contract method to match method spec"

    with pytest.raises(Exception):
        app.contract.get_method_by_name("made up")


def test_internal_not_exposed():
    class SingleInternal(Application):
        pass

    app = SingleInternal()

    @app.external
    def doit(*, output: pt.abi.Bool):
        return do_permissioned_thing(output=output)

    def do_permissioned_thing(*, output: pt.abi.Bool):
        return pt.Seq((b := pt.abi.Bool()).set(pt.Int(1)), output.set(b))

    assert len(app.abi_methods) == 1, "Expected a single external"


def test_method_override():
    app = Application()

    @app.external(name="handle")
    def handle_algo(txn: PaymentTransaction):
        return pt.Approve()

    @app.external(name="handle")
    def handle_asa(txn: AssetTransferTransaction):
        return pt.Approve()

    app.compile()
    assert app.contract

    assert app.abi_methods == {"handle_algo": handle_algo, "handle_asa": handle_asa}

    overlapping_methods = [
        method for method in app.contract.methods if method.name == "handle"
    ]
    assert isinstance(handle_algo, pt.ABIReturnSubroutine)
    assert isinstance(handle_asa, pt.ABIReturnSubroutine)
    assert overlapping_methods == [handle_algo.method_spec(), handle_asa.method_spec()]


def test_bare():
    app = NoCreateApp()

    @app.create(bare=True)
    def create():
        return pt.Approve()

    @app.update(bare=True)
    def update():
        return pt.Approve()

    @app.delete(bare=True)
    def delete():
        return pt.Approve()

    assert len(app.bare_methods) == 3, "Expected 3 bare externals: create,update,delete"


def test_mixed_bares():
    class MixedBare(NoCreateApp):
        pass

    app = MixedBare()

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
    app = Application()

    @app.external()
    def handle():
        return pt.Assert(pt.Int(1))

    @app.external(override=True, name="handle")
    def handle_2():
        return pt.Assert(pt.Int(2))

    app.compile()
    assert app.contract

    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert list(app.abi_methods) == ["handle_2"]
    assert (
        app.contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"


def test_application_external_override_false():
    app = Application()

    @app.external
    def handle():
        return pt.Assert(pt.Int(1))

    with pytest.raises(ValueError):

        @app.external(override=False, name="handle")
        def handle_2():
            return pt.Assert(pt.Int(2))


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_external_override_none(create_existing_handle: bool):
    app = Application()

    if create_existing_handle:

        @app.external
        def handle():
            return pt.Assert(pt.Int(1))

    @app.external(override=None, name="handle")
    def handle_2():
        return pt.Assert(pt.Int(2))

    app.compile()
    assert app.contract
    assert isinstance(handle_2, pt.ABIReturnSubroutine)

    assert (
        app.contract.get_method_by_name("handle") == handle_2.method_spec()
    ), "Expected contract method to match method spec"
    assert list(app.abi_methods) == ["handle_2"]


def test_application_bare_override_true():
    app = NoCreateApp()

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
    app = NoCreateApp()

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


@pytest.mark.parametrize("create_existing_handle", [True, False])
def test_application_bare_override_none(create_existing_handle: bool):
    app = NoCreateApp()

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


def test_app_state():
    class BasicAppState(Application):
        uint_val: Final[ApplicationStateValue] = ApplicationStateValue(
            stack_type=pt.TealType.uint64
        )
        byte_val: Final[ApplicationStateValue] = ApplicationStateValue(
            stack_type=pt.TealType.bytes
        )

    app = BasicAppState()

    assert app.app_state.num_uints == 1, "Expected 1 int"
    assert app.app_state.num_byte_slices == 1, "Expected 1 byte slice"

    class ReservedAppState(BasicAppState):
        uint_dynamic: Final[
            ReservedApplicationStateValue
        ] = ReservedApplicationStateValue(stack_type=pt.TealType.uint64, max_keys=10)
        byte_dynamic: Final[
            ReservedApplicationStateValue
        ] = ReservedApplicationStateValue(stack_type=pt.TealType.bytes, max_keys=10)

    app = ReservedAppState()
    assert app.app_state.num_uints == 11, "Expected 11 ints"
    assert app.app_state.num_byte_slices == 11, "Expected 11 byte slices"


def test_acct_state():
    class BasicAcctState(Application):
        uint_val: Final[AccountStateValue] = AccountStateValue(
            stack_type=pt.TealType.uint64
        )
        byte_val: Final[AccountStateValue] = AccountStateValue(
            stack_type=pt.TealType.bytes
        )

    app = BasicAcctState()

    assert app.acct_state.num_uints == 1, "Expected 1 int"
    assert app.acct_state.num_byte_slices == 1, "Expected 1 byte slice"

    class ReservedAcctState(BasicAcctState):
        uint_dynamic: Final[ReservedAccountStateValue] = ReservedAccountStateValue(
            stack_type=pt.TealType.uint64, max_keys=5
        )
        byte_dynamic: Final[ReservedAccountStateValue] = ReservedAccountStateValue(
            stack_type=pt.TealType.bytes, max_keys=5
        )

    app = ReservedAcctState()
    assert app.acct_state.num_uints == 6, "Expected 6 ints"
    assert app.acct_state.num_byte_slices == 6, "Expected 6 byte slices"


def test_default_param_state():
    class Hinty(Application):
        asset_id = ApplicationStateValue(pt.TealType.uint64, default=pt.Int(123))

    h = Hinty()

    @h.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = h.asset_id,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == h.asset_id)

    assert "hintymeth" in h.hints, "Expected a hint available for the method"

    hint = h.hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default.resolvable_class == DefaultArgumentClass.GlobalState
    assert (
        default.resolve_hint() == Hinty.asset_id.str_key()
    ), "Expected the hint to match the method spec"


def test_default_param_const():
    const_val = 123

    app = Application()

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = const_val,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    assert "hintymeth" in app.hints, "Expected a hint available for the method"

    hint = app.hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert default.resolvable_class == DefaultArgumentClass.Constant
    assert (
        default.resolve_hint() == const_val
    ), "Expected the hint to match the method spec"


def test_default_read_only_method():
    const_val = 123

    app = Application()

    @app.external(read_only=True)
    def get_asset_id(*, output: pt.abi.Uint64):
        return output.set(pt.Int(const_val))

    @app.external
    def hintymeth(
        num: pt.abi.Uint64,
        aid: pt.abi.Asset = get_asset_id,  # type: ignore[assignment]
    ):
        return pt.Assert(aid.asset_id() == pt.Int(const_val))

    assert "hintymeth" in app.hints, "Expected a hint available for the method"

    hint = app.hints["hintymeth"]

    assert "aid" in hint.default_arguments, "Expected annotation available for param"

    default = hint.default_arguments["aid"]

    assert isinstance(get_asset_id, pt.ABIReturnSubroutine)
    assert default.resolvable_class == DefaultArgumentClass.ABIMethod
    assert (
        default.resolve_hint() == get_asset_id.method_spec().dictify()
    ), "Expected the hint to match the method spec"


def test_app_spec():
    class Specd(Application):
        decl_app_val = ApplicationStateValue(pt.TealType.uint64)
        decl_acct_val = AccountStateValue(pt.TealType.uint64)

    app = Specd()

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

    app.compile()

    actual_spec = app.application_spec()

    get_asset_id_hints = {"read_only": True}
    annotated_meth_hints = {
        "default_arguments": {
            "aid": {
                "source": "abi-method",
                "data": {
                    "name": "get_asset_id",
                    "args": [],
                    "returns": {"type": "uint64"},
                },
            },
        }
    }
    struct_meth_hints = {
        "structs": {
            "thing": {"name": "Thing", "elements": [("a", "uint64"), ("b", "uint32")]}
        }
    }

    expected_hints = {
        "get_asset_id": get_asset_id_hints,
        "annotated_meth": annotated_meth_hints,
        "struct_meth": struct_meth_hints,
    }

    expected_schema = {
        "local": {
            "declared": {
                "decl_acct_val": {
                    "type": "uint64",
                    "key": "decl_acct_val",
                    "descr": "",
                }
            },
            "reserved": {},
        },
        "global": {
            "declared": {
                "decl_app_val": {
                    "type": "uint64",
                    "key": "decl_app_val",
                    "descr": "",
                }
            },
            "reserved": {},
        },
    }

    def dict_match(a: dict, e: dict) -> bool:
        for k, v in a.items():
            if type(v) is dict:
                if not dict_match(v, e[k]):
                    print(f"comparing {k} {v} {e[k]}")
                    return False
            else:
                if v != e[k]:
                    print(f"comparing {k}")
                    return False

        return True

    assert dict_match(actual_spec["hints"], expected_hints)
    assert dict_match(actual_spec["schema"], expected_schema)


EXPECTED_BARE_HANDLERS = [
    "create",
]


def test_struct_args():
    from algosdk.abi import Method, Argument, Returns

    class UserRecord(pt.abi.NamedTuple):
        addr: pt.abi.Field[pt.abi.Address]
        balance: pt.abi.Field[pt.abi.Uint64]
        nickname: pt.abi.Field[pt.abi.String]

    app = Application()

    @app.external
    def structy(user_record: UserRecord):
        return pt.Assert(pt.Int(1))

    arg = Argument("(address,uint64,string)", name="user_record")
    ret = Returns("void")
    assert Method("structy", [arg], ret) == structy.method_spec()

    assert app.hints["structy"].structs == {
        "user_record": {
            "name": "UserRecord",
            "elements": [
                ("addr", "address"),
                ("balance", "uint64"),
                ("nickname", "string"),
            ],
        }
    }


def test_instance_vars():
    def Inst(value: str) -> Application:
        app = Application()

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
    i1.compile()
    assert i1.approval_program

    i2 = Inst("second")
    i2.compile()
    assert i2.approval_program

    assert i1.approval_program.index("first") > 0, "Expected to see the string `first`"
    assert (
        i2.approval_program.index("second") > 0
    ), "Expected to see the string `second`"

    with pytest.raises(ValueError):
        i1.approval_program.index("second")

    with pytest.raises(ValueError):
        i2.approval_program.index("first")


def hashy(sig: str):
    chksum = SHA512.new(truncate="256")
    chksum.update(sig.encode())
    return chksum.digest()[:4]


def test_abi_method_details():
    app = Application()

    @app.external
    def meth():
        return pt.Assert(pt.Int(1))

    expected_sig = "meth()void"
    expected_selector = hashy(expected_sig)

    method_spec = meth.method_spec()
    assert method_spec.get_signature() == expected_sig
    assert method_spec.get_selector() == expected_selector


def test_multi_optin():
    test = Application()

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt1(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64):
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    @test.external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def opt2(txn: pt.abi.AssetTransferTransaction, amount: pt.abi.Uint64):
        return pt.Seq(pt.Assert(txn.get().asset_amount() == amount.get()))

    test.compile()
