import pytest
import json
from typing import Final, cast, Annotated
from Cryptodome.Hash import SHA512
import pyteal as pt

from beaker.state import (
    DynamicApplicationStateValue,
    ApplicationStateValue,
    AccountStateValue,
    DynamicAccountStateValue,
)

from beaker.errors import BareOverwriteError
from beaker.application import (
    Application,
    get_method_selector,
    get_method_signature,
    get_method_spec,
)
from beaker.decorators import (
    ParameterAnnotation,
    DefaultArgument,
    DefaultArgumentClass,
    external,
    internal,
    create,
    update,
    delete,
)

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_empty_application():
    class EmptyApp(Application):
        pass

    ea = EmptyApp()

    assert ea.router.name == "EmptyApp", "Expected router name to match class"
    assert (
        ea.acct_state.num_uints
        + ea.acct_state.num_byte_slices
        + ea.app_state.num_uints
        + ea.app_state.num_byte_slices
        == 0
    ), "Expected no schema"

    assert len(ea.bare_externals.keys()) == len(
        EXPECTED_BARE_HANDLERS
    ), f"Expected {len(EXPECTED_BARE_HANDLERS)} bare handlers: {EXPECTED_BARE_HANDLERS}"
    assert (
        len(ea.approval_program) > 0
    ), "Expected approval program to be compiled to teal"
    assert len(ea.clear_program) > 0, "Expected clear program to be compiled to teal"
    assert len(ea.contract.methods) == 0, "Expected no methods in the contract"


def test_teal_version():
    class EmptyApp(Application):
        pass

    ea = EmptyApp(version=4)

    assert ea.teal_version == 4, "Expected teal v4"
    assert ea.approval_program.split("\n")[0] == "#pragma version 4"


def test_single_external():
    class Singleexternal(Application):
        @external
        def handle():
            return pt.Assert(pt.Int(1))

    sh = Singleexternal()

    assert len(sh.methods) == 1, "Expected a single external"
    assert sh.contract.get_method_by_name("handle") == get_method_spec(
        sh.handle
    ), "Expected contract method to match method spec"

    with pytest.raises(Exception):
        sh.contract.get_method_by_name("made up")


def test_bare_external():
    class Bareexternal(Application):
        @create
        def create():
            return pt.Approve()

        @update
        def update():
            return pt.Approve()

        @delete
        def delete():
            return pt.Approve()

    bh = Bareexternal()

    assert (
        len(bh.bare_externals) == 3
    ), "Expected 4 bare externals: create,update,delete"

    class FailBareexternal(Application):
        @create
        def wrong_name():
            return pt.Approve()

    with pytest.raises(BareOverwriteError):
        bh = FailBareexternal()


def test_subclass_application():
    class SuperClass(Application):
        @external
        def handle():
            return pt.Assert(pt.Int(1))

    class SubClass(SuperClass):
        pass

    sc = SubClass()
    assert len(sc.methods) == 1, "Expected single method"
    assert sc.contract.get_method_by_name("handle") == get_method_spec(
        sc.handle
    ), "Expected contract method to match method spec"

    class OverrideSubClass(SuperClass):
        @external
        def handle():
            return pt.Assert(pt.Int(2))

    osc = OverrideSubClass()
    assert len(osc.methods) == 1, "Expected single method"
    assert osc.contract.get_method_by_name("handle") == get_method_spec(
        osc.handle
    ), "Expected contract method to match method spec"


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

    class DynamicAppState(BasicAppState):
        uint_dynamic: Final[
            DynamicApplicationStateValue
        ] = DynamicApplicationStateValue(stack_type=pt.TealType.uint64, max_keys=10)
        byte_dynamic: Final[
            DynamicApplicationStateValue
        ] = DynamicApplicationStateValue(stack_type=pt.TealType.bytes, max_keys=10)

    app = DynamicAppState()
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

    class DynamicAcctState(BasicAcctState):
        uint_dynamic: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
            stack_type=pt.TealType.uint64, max_keys=5
        )
        byte_dynamic: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
            stack_type=pt.TealType.bytes, max_keys=5
        )

    app = DynamicAcctState()
    assert app.acct_state.num_uints == 6, "Expected 6 ints"
    assert app.acct_state.num_byte_slices == 6, "Expected 6 byte slices"


def test_internal():
    from beaker.decorators import internal

    class Internal(Application):
        @create
        def create(self):
            return pt.Seq(
                pt.Pop(self.internal_meth()),
                pt.Pop(self.internal_meth_no_self()),
                pt.Pop(self.subr_no_self()),
            )

        @external(method_config=pt.MethodConfig(no_op=pt.CallConfig.CALL))
        def otherthing():
            return pt.Seq(
                pt.Pop(Internal.internal_meth_no_self()),
                pt.Pop(Internal.subr_no_self()),
            )

        @internal(pt.TealType.uint64)
        def internal_meth(self):
            return pt.Int(1)

        @internal(pt.TealType.uint64)
        def internal_meth_no_self():
            return pt.Int(1)

        # Cannot be called with `self` specified
        @pt.Subroutine(pt.TealType.uint64)
        def subr(self):
            return pt.Int(1)

        @pt.Subroutine(pt.TealType.uint64)
        def subr_no_self():
            return pt.Int(1)

    i = Internal()
    assert len(i.methods) == 1, "Expected 1 ABI method"

    # Test with self
    meth = cast(pt.SubroutineFnWrapper, i.internal_meth)
    expected = pt.SubroutineCall(meth.subroutine, []).__teal__(options)

    actual = i.internal_meth().__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    # Cannot call it without instantiated object
    with pytest.raises(Exception):
        Internal.internal_meth()

    # Test with no self
    meth = cast(pt.SubroutineFnWrapper, i.internal_meth_no_self)
    expected = pt.SubroutineCall(meth.subroutine, []).__teal__(options)

    actual = i.internal_meth_no_self().__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    # Cannot call a subroutine that references self
    with pytest.raises(pt.TealInputError):
        i.subr()

    # Test subr with no self
    meth = cast(pt.SubroutineFnWrapper, i.subr_no_self)
    expected = pt.SubroutineCall(meth.subroutine, []).__teal__(options)
    actual = i.subr_no_self().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_hints():
    class Hinty(Application):
        @external(read_only=True)
        def get_asset_id(self, *, output: pt.abi.Uint64):
            return output.set(pt.Int(123))

        @external
        def hintymeth(
            self,
            aid: Annotated[
                pt.abi.Asset,
                ParameterAnnotation(descr="Testing asset id", default=get_asset_id),
            ],
            num: pt.abi.Uint64,
        ):
            return pt.Assert(pt.Int(1))

    h = Hinty()

    assert h.hintymeth.__name__ in h.hints, "Expected a hint available for the method"

    hint = h.hints[h.hintymeth.__name__]

    assert "aid" in hint.param_annotations, "Expected annotation available for param"
    anno = hint.param_annotations["aid"]

    assert anno.descr == "Testing asset id"

    assert anno.default is not None
    default = DefaultArgument(anno.default)
    assert default.resolvable_class == DefaultArgumentClass.ABIMethod
    assert (
        default.resolve_hint() == get_method_spec(h.get_asset_id).dictify()
    ), "Expected the hint to match the method spec"


def test_app_spec():
    class Specd(Application):
        decl_app_val = ApplicationStateValue(pt.TealType.uint64)
        decl_acct_val = AccountStateValue(pt.TealType.uint64)

        @external(read_only=True)
        def get_asset_id(self, *, output: pt.abi.Uint64):
            return output.set(pt.Int(123))

        @external
        def annotated_meth(
            self,
            aid: Annotated[
                pt.abi.Asset,
                ParameterAnnotation(descr="Testing asset id", default=get_asset_id),
            ],
        ):
            return pt.Assert(pt.Int(1))

        class Thing(pt.abi.NamedTuple):
            a: pt.abi.Field[pt.abi.Uint64]
            b: pt.abi.Field[pt.abi.Uint32]

        @external
        def struct_meth(self, thing: Thing):
            return pt.Approve()

    s = Specd()

    actual_spec = s.application_spec()
    expected_spec = {
        "hints": {
            "get_asset_id": {"read_only": True},
            "annotated_meth": {
                "param_annotations": {
                    "aid": {
                        "descr": "Testing asset id",
                        "default": {
                            "abi-method": {
                                "name": "get_asset_id",
                                "args": [],
                                "returns": {"type": "uint64"},
                            }
                        },
                    }
                }
            },
            "struct_meth": {
                "structs": {"thing": {"name": "Thing", "elements": ["a", "b"]}}
            },
        },
        "schema": {
            "local": {
                "declared": {
                    "decl_acct_val": {
                        "type": "uint64",
                        "key": "decl_acct_val",
                        "descr": None,
                    }
                },
                "dynamic": {},
            },
            "global": {
                "declared": {
                    "decl_app_val": {
                        "type": "uint64",
                        "key": "decl_app_val",
                        "descr": None,
                    }
                },
                "dynamic": {},
            },
        },
        "contract": {
            "name": "Specd",
            "methods": [
                # {"name": "get_asset_id", "args": [], "returns": {"type": "uint64"}},
                # {
                #    "name": "annotated_meth",
                #    "args": [ {"type": "asset", "name": "aid", "desc": "Testing asset id"} ],
                #    "returns": {"type": "void"},
                # },
                # {
                #    "name": "struct_meth",
                #    "args": [{"type": "(uint64,uint32)", "name": "thing"}],
                #    "returns": {"type": "void"},
                # },
            ],
            "desc": None,
            "networks": {},
        },
    }

    # TODO: come back and check methods, the sorting gets weird
    actual_spec["contract"]["methods"] = []
    del actual_spec["source"]

    assert json.dumps(actual_spec, sort_keys=True) == json.dumps(
        expected_spec, sort_keys=True
    )


EXPECTED_BARE_HANDLERS = [
    "create",
]


def test_model_args():
    from algosdk.abi import Method, Argument, Returns

    class Structed(Application):
        class UserRecord(pt.abi.NamedTuple):
            addr: pt.abi.Field[pt.abi.Address]
            balance: pt.abi.Field[pt.abi.Uint64]
            nickname: pt.abi.Field[pt.abi.String]

        @external
        def structy(self, user_record: UserRecord):
            return pt.Assert(pt.Int(1))

    m = Structed()

    arg = Argument("(address,uint64,string)", name="user_record")
    ret = Returns("void")
    assert Method("structy", [arg], ret) == get_method_spec(m.structy)

    assert m.hints["structy"].structs == {
        "user_record": {
            "name": "UserRecord",
            "elements": ["addr", "balance", "nickname"],
        }
    }


def test_instance_vars():
    class Inst(Application):
        def __init__(self, v: str):
            self.v = pt.Bytes(v)
            super().__init__()

        @external
        def use_it(self):
            return pt.Log(self.v)

        @external
        def call_it(self):
            return self.use_it_internal()

        @internal(pt.TealType.none)
        def use_it_internal(self):
            return pt.Log(self.v)

    i1 = Inst("first")
    i2 = Inst("second")

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
    @external
    def meth():
        return pt.Assert(pt.Int(1))

    expected_sig = "meth()void"
    expected_selector = hashy(expected_sig)

    assert get_method_signature(meth) == expected_sig
    assert get_method_selector(meth) == expected_selector

    def meth2():
        pass

    with pytest.raises(Exception):
        get_method_spec(meth2)

    with pytest.raises(Exception):
        get_method_signature(meth2)

    with pytest.raises(Exception):
        get_method_selector(meth2)
