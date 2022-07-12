from inspect import stack
import pytest
from typing import Final
import pyteal as pt

from beaker.application_schema import (
    DynamicGlobalStateValue,
    GlobalStateValue,
    LocalStateValue,
    DynamicLocalStateValue,
)

from .errors import BareOverwriteError
from .application import Application
from .decorators import get_handler_config, handler, Bare


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