import pytest
from typing import Final, cast
import pyteal as pt

from beaker.application_schema import (
    DynamicGlobalStateValue,
    GlobalStateValue,
    LocalStateValue,
    DynamicLocalStateValue,
)

from .errors import BareOverwriteError
from .application import Application,method_spec
from .decorators import ResolvableArguments, get_handler_config, handler, Bare
from .model import Model

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

    assert (
        len(ea.bare_handlers.keys()) == 3
    ), "Expected 3 bare handlers: create, update, and delete"
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


def test_single_handler():
    class SingleHandler(Application):
        @handler
        def handle():
            return pt.Assert(pt.Int(1))

    sh = SingleHandler()

    assert len(sh.methods) == 1, "Expected a single handler"

    hc = get_handler_config(sh.handle)
    assert (
        sh.contract.get_method_by_name("handle") == hc.abi_method.method_spec()
    ), "Expected contract method to match method spec"

    with pytest.raises(Exception):
        sh.contract.get_method_by_name("made up")


def test_bare_handler():
    class BareHandler(Application):
        @Bare.create
        def create():
            return pt.Approve()

        @Bare.update
        def update():
            return pt.Approve()

        @Bare.delete
        def delete():
            return pt.Approve()

    bh = BareHandler()
    assert (
        len(bh.bare_handlers) == 3
    ), "Expected 3 bare handlers: create, update, delete"

    class FailBareHandler(Application):
        @Bare.create
        def wrong_name():
            return pt.Approve()

    with pytest.raises(BareOverwriteError):
        bh = FailBareHandler()


def test_subclass_application():
    class SuperClass(Application):
        @handler
        def handle():
            return pt.Assert(pt.Int(1))

    class SubClass(SuperClass):
        pass

    sc = SubClass()
    assert len(sc.methods) == 1, "Expected single method"
    hc = get_handler_config(sc.handle)
    assert (
        sc.contract.get_method_by_name("handle") == hc.abi_method.method_spec()
    ), "Expected contract method to match method spec"

    class OverrideSubClass(SuperClass):
        @handler
        def handle():
            return pt.Assert(pt.Int(2))

    osc = OverrideSubClass()
    assert len(osc.methods) == 1, "Expected single method"
    hc = get_handler_config(osc.handle)
    assert (
        osc.contract.get_method_by_name("handle") == hc.abi_method.method_spec()
    ), "Expected contract method to match method spec"


def test_app_state():
    class BasicAppState(Application):
        uint_val: Final[GlobalStateValue] = GlobalStateValue(
            stack_type=pt.TealType.uint64
        )
        byte_val: Final[GlobalStateValue] = GlobalStateValue(
            stack_type=pt.TealType.bytes
        )

    app = BasicAppState()

    assert app.app_state.num_uints == 1, "Expected 1 int"
    assert app.app_state.num_byte_slices == 1, "Expected 1 byte slice"

    class DynamicAppState(BasicAppState):
        uint_dynamic: Final[DynamicGlobalStateValue] = DynamicGlobalStateValue(
            stack_type=pt.TealType.uint64, max_keys=10
        )
        byte_dynamic: Final[DynamicGlobalStateValue] = DynamicGlobalStateValue(
            stack_type=pt.TealType.bytes, max_keys=10
        )

    app = DynamicAppState()
    assert app.app_state.num_uints == 11, "Expected 11 ints"
    assert app.app_state.num_byte_slices == 11, "Expected 11 byte slices"


def test_acct_state():
    class BasicAcctState(Application):
        uint_val: Final[LocalStateValue] = LocalStateValue(
            stack_type=pt.TealType.uint64
        )
        byte_val: Final[LocalStateValue] = LocalStateValue(stack_type=pt.TealType.bytes)

    app = BasicAcctState()

    assert app.acct_state.num_uints == 1, "Expected 1 int"
    assert app.acct_state.num_byte_slices == 1, "Expected 1 byte slice"

    class DynamicAcctState(BasicAcctState):
        uint_dynamic: Final[DynamicLocalStateValue] = DynamicLocalStateValue(
            stack_type=pt.TealType.uint64, max_keys=10
        )
        byte_dynamic: Final[DynamicLocalStateValue] = DynamicLocalStateValue(
            stack_type=pt.TealType.bytes, max_keys=10
        )

    app = DynamicAcctState()
    assert app.acct_state.num_uints == 11, "Expected 11 ints"
    assert app.acct_state.num_byte_slices == 11, "Expected 11 byte slices"


def test_internal():
    from beaker.decorators import internal

    class Internal(Application):
        @Bare.create
        def create(self):
            return pt.Seq(
                pt.Pop(self.internal_meth()),
                pt.Pop(self.internal_meth_no_self()),
                pt.Pop(self.subr_no_self()),
            )

        @handler(method_config=pt.MethodConfig(no_op=pt.CallConfig.CALL))
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


def test_contract_hints():
    class Hinty(Application):

        @handler
        def get_asset_id(*, output: pt.abi.Uint64):
            return output.set(pt.Int(123))

        @handler(
            resolvable=ResolvableArguments(
                aid=get_asset_id
            )
        )
        def hintymeth(aid: pt.abi.Asset):
            return pt.Assert(pt.Int(1))
        

    h = Hinty()
    hints = h.contract_hints()

    assert h.hintymeth.__name__ in hints, "Expected a hint available for the method"

    hint = hints[h.hintymeth.__name__]
    assert hint.resolvable['aid'] == method_spec(h.get_asset_id), "Expected the hint to match the method spec"


def test_model_args():
    from algosdk.abi import Method, Argument, Returns
    class Modeled(Application):
        class UserRecord(Model):
            addr: pt.abi.Address
            balance: pt.abi.Uint64
            nickname: pt.abi.String

        @handler
        def modely(user_record: UserRecord):
            return pt.Assert(pt.Int(1))

    m = Modeled()

    arg = Argument('(address,uint64,string)', name='user_record')
    ret = Returns('void')
    assert Method("modely", [arg], ret)  == method_spec(m.modely)
