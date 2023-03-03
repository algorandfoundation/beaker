import contextlib
import re
from typing import Any

import pyteal as pt
import pytest

from beaker import Application, Authorize
from beaker.application import _default_argument_from_resolver

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_external_read_only() -> None:
    app = Application("")

    @app.external(read_only=True)
    def handleable() -> pt.Expr:
        return pt.Approve()

    assert isinstance(handleable, pt.ABIReturnSubroutine)
    assert "handleable()void" in app.abi_externals

    assert app.build().dictify()["hints"]["handleable()void"].get("read_only") is True


def test_authorize_only() -> None:
    auth_only = Authorize.only(pt.Global.creator_address())

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only.subroutine.implementation(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_external_authorize() -> None:
    app = Application("")
    cmt = "unauthorized"
    auth_only = Authorize.only(pt.Global.creator_address())

    @app.external(authorize=auth_only)
    def creator_only() -> pt.Expr:
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = creator_only.subroutine.implementation().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_authorize_holds_token() -> None:

    with pytest.raises(pt.TealTypeError):
        Authorize.only(pt.Int(1))

    asset_id = pt.Int(123)
    auth_holds_token = Authorize.holds_token(asset_id)

    balance = pt.AssetHolding.balance(pt.Txn.sender(), asset_id)
    expr = pt.Seq(balance, pt.And(balance.hasValue(), balance.value() > pt.Int(0)))
    expected = expr.__teal__(options)
    actual = auth_holds_token.subroutine.implementation(pt.Txn.sender()).__teal__(
        options
    )

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected


def test_external_authorize_holds_token() -> None:
    cmt = "unauthorized"
    app = Application("")
    asset_id = pt.Int(123)
    auth_holds_token = Authorize.holds_token(asset_id)

    @app.external(authorize=auth_holds_token)
    def holds_token_only() -> pt.Expr:
        return pt.Approve()

    expr = pt.Seq(
        pt.Assert(auth_holds_token(pt.Txn.sender()), comment=cmt), pt.Approve()
    )

    expected = expr.__teal__(options)
    actual = holds_token_only.subroutine.implementation().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_authorize_opted_in() -> None:

    with pytest.raises(pt.TealTypeError):
        Authorize.holds_token(pt.Bytes("abc"))

    app_id = pt.Int(123)
    auth_opted_in = Authorize.opted_in(app_id)

    expr = pt.App.optedIn(pt.Txn.sender(), app_id)

    expected = expr.__teal__(options)
    actual = auth_opted_in.subroutine.implementation(pt.Txn.sender()).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected


def test_external_authorize_opted_in() -> None:
    app = Application("")
    cmt = "unauthorized"
    app_id = pt.Int(123)
    auth_opted_in = Authorize.opted_in(app_id)

    @app.external(authorize=auth_opted_in)
    def opted_in_only() -> pt.Expr:
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_opted_in(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = opted_in_only.subroutine.implementation().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_authorize_bare_handler() -> None:
    app = Application("")
    cmt = "unauthorized"
    auth_only = Authorize.only(pt.Global.creator_address())

    @app.delete(authorize=auth_only)
    def deleter() -> pt.Expr:
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = deleter.subroutine.implementation().__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        Authorize.opted_in(pt.Bytes("abc"))

    with pytest.raises(pt.TealInputError):

        @pt.Subroutine(pt.TealType.uint64)
        def thing(a: pt.Expr, b: pt.Expr) -> pt.Expr:
            return pt.Int(1)

        @app.external(authorize=thing)
        def other_thing() -> pt.Expr:
            return pt.Approve()

    with pytest.raises(pt.TealTypeError):

        @pt.Subroutine(pt.TealType.bytes)
        def thing(x: pt.Expr) -> pt.Expr:
            return pt.Bytes("fail")

        @app.external(authorize=thing)
        def other_other_thing() -> pt.Expr:
            return pt.Approve()


def test_named_tuple() -> None:
    class Order(pt.abi.NamedTuple):
        item: pt.abi.Field[pt.abi.String]
        count: pt.abi.Field[pt.abi.Uint64]

    app = Application("")

    @app.external
    def thing(o: Order) -> pt.Expr:
        return pt.Approve()

    hints = app.build().hints
    assert hints is not None
    thing_hints = hints.get("thing((string,uint64))void")
    assert thing_hints is not None
    assert thing_hints.structs is not None
    o_hint = thing_hints.structs.get("o")
    assert o_hint == {
        "name": "Order",
        "elements": [["item", "string"], ["count", "uint64"]],
    }


@pytest.mark.parametrize(
    "decorator_name,action_name",
    [
        ("create", "no_op"),
        ("no_op", "no_op"),
        ("delete", "delete_application"),
        ("update", "update_application"),
        ("opt_in", "opt_in"),
        ("close_out", "close_out"),
    ],
)
def test_decorators_with_bare_signature(decorator_name: str, action_name: str) -> None:
    app = Application("")
    decorator = getattr(app, decorator_name)

    @decorator(bare=True)
    def test() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(test, pt.SubroutineFnWrapper)
    assert action_name in app.bare_actions


def test_bare_clear_state() -> None:
    app = Application("clear_state")

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(clear_state, pt.SubroutineFnWrapper)
    assert "clear_state" not in app.bare_actions
    assert app._clear_state_method is clear_state


def test_non_bare_clear_state() -> None:
    app = Application("clear_state")

    with pytest.raises(TypeError):

        @app.clear_state  # type: ignore
        def clear_state(value: pt.abi.Uint64) -> pt.Expr:
            return pt.Approve()


def test_bare_external() -> None:
    app = Application("bare_external")

    @app.external(bare=True, method_config=pt.MethodConfig(no_op=pt.CallConfig.ALL))
    def external() -> pt.Expr:
        return pt.Approve()

    assert isinstance(external, pt.SubroutineFnWrapper)
    assert "no_op" in app.bare_actions


@pytest.mark.parametrize(
    "config", [pt.CallConfig.CREATE, pt.CallConfig.CALL, pt.CallConfig.ALL]
)
def test_external_method_config(config: pt.CallConfig) -> None:
    app = Application("")

    @app.external(method_config=pt.MethodConfig(no_op=config))
    def external() -> pt.Expr:
        return pt.Approve()

    app_spec = app.build()
    assert app_spec.hints["external()void"].call_config.no_op == config


def test_local_state_resolvable() -> None:
    from beaker.state import LocalStateValue

    x = LocalStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = _default_argument_from_resolver(x)
    assert r["source"] == "local-state"


def test_reserved_local_state_resolvable() -> None:
    from beaker.state import ReservedLocalStateValue

    x = ReservedLocalStateValue(pt.TealType.uint64, max_keys=1)
    r = _default_argument_from_resolver(x[pt.Bytes("x")])
    assert r["source"] == "local-state"


def test_application_state_resolvable() -> None:
    from beaker.state import GlobalStateValue

    x = GlobalStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = _default_argument_from_resolver(x)
    assert r["source"] == "global-state"


def test_reserved_application_state_resolvable() -> None:
    from beaker.state import (
        ReservedGlobalStateValue,
    )

    x = ReservedGlobalStateValue(pt.TealType.uint64, max_keys=1)
    r = _default_argument_from_resolver(x[pt.Bytes("x")])
    assert r["source"] == "global-state"


def test_abi_method_resolvable() -> None:
    app = Application("")

    @app.external(read_only=True)
    def x(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(pt.Int(1))

    @app.external
    def y(
        x_val: pt.abi.Uint64 = x,  # type: ignore[assignment]
    ) -> pt.Expr:
        return pt.Assert(x_val.get() == pt.Int(1))

    app_spec = app.build()
    assert (
        app_spec.hints[y.method_signature()].default_arguments["x_val"]["source"]
        == "abi-method"
    )


def test_bytes_constant_resolvable() -> None:
    r = _default_argument_from_resolver(pt.Bytes("1"))
    assert r["source"] == "constant"


def test_int_constant_resolvable() -> None:
    r = _default_argument_from_resolver(pt.Int(1))
    assert r["source"] == "constant"


def test_abi_override_true_nothing_to_override() -> None:
    app = Application("")

    with pytest.raises(ValueError, match="override=True, but nothing to override"):

        @app.external(override=True)
        def handle() -> pt.Expr:
            return pt.Assert(pt.Int(1))


def test_bare_override_true_nothing_to_override() -> None:
    app = Application("")

    with pytest.raises(ValueError, match="override=True, but nothing to override"):

        @app.opt_in(override=True, bare=True)
        def handle() -> pt.Expr:
            return pt.Approve()


def test_clear_state_override_true_nothing_to_override() -> None:
    app = Application("")

    with pytest.raises(ValueError, match="override=True, but no clear_state defined"):

        @app.clear_state(override=True)
        def handle() -> pt.Expr:
            return pt.Approve()


def test_clear_state_prevent_accidental_override() -> None:
    app = Application("")

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(
        ValueError, match="override=False, but clear_state already defined"
    ):

        @app.clear_state
        def handle() -> pt.Expr:
            return pt.Approve()


def test_abi_external_prevent_accidental_override() -> None:
    app = Application("")

    @app.external
    def method() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(
        ValueError,
        match="override=False, but method with matching signature already registered",
    ):

        @app.external(name="method")
        def handle() -> pt.Expr:
            return pt.Approve()


def test_bare_external_prevent_accidental_override() -> None:
    app = Application("")

    @app.create(bare=True)
    def method() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(
        ValueError,
        match="override=False, but bare external for no_op already exists",
    ):

        @app.create(bare=True)
        def handle() -> pt.Expr:
            return pt.Approve()


def test_clear_state_override() -> None:
    app = Application("")

    @app.clear_state
    def old() -> pt.Expr:
        return pt.Approve()

    @app.clear_state(override=True)
    def new() -> pt.Expr:
        return pt.Approve()

    assert app._clear_state_method is new


def test_bare_external_invalid_options() -> None:
    app = Application("")
    with pytest.raises(
        ValueError, match=re.escape("@external(bare=True, ...) requires method_config")
    ):

        @app.external(bare=True)
        def method() -> pt.Expr:
            return pt.Approve()

    with pytest.raises(
        ValueError, match="read_only=True has no effect on bare methods"
    ):

        @app.external(
            bare=True, method_config={"no_op": pt.CallConfig.CALL}, read_only=True
        )
        def method2() -> pt.Expr:
            return pt.Approve()

    with pytest.raises(TypeError, match="Bare methods must take no method arguments"):

        @app.external(bare=True, method_config={"no_op": pt.CallConfig.CALL})  # type: ignore[arg-type]
        def method3(a: pt.Expr) -> pt.Expr:
            return pt.Assert(a)


def test_no_op_call_config_permutations() -> None:
    app = Application("")

    @app.no_op
    def no_op_default() -> pt.Expr:
        return pt.Approve()

    for allow_call in (True, False):
        for allow_create in (True, False):
            if not (allow_call or allow_create):
                ctx: Any = pytest.raises(
                    ValueError,
                    match="Require one of allow_call or allow_create to be True",
                )
            else:
                ctx = contextlib.nullcontext()
            with ctx:

                @app.no_op(
                    allow_call=allow_call,
                    allow_create=allow_create,
                    name=f"no_op_allow_call={allow_call}_allow_create={allow_create}",
                )
                def no_op_() -> pt.Expr:
                    return pt.Approve()

    app_spec = app.build()
    assert app_spec.dictify()["hints"] == {
        "no_op_default()void": {"call_config": {"no_op": "CALL"}},
        "no_op_allow_call=True_allow_create=True()void": {
            "call_config": {"no_op": "ALL"}
        },
        "no_op_allow_call=True_allow_create=False()void": {
            "call_config": {"no_op": "CALL"}
        },
        "no_op_allow_call=False_allow_create=True()void": {
            "call_config": {"no_op": "CREATE"}
        },
    }
