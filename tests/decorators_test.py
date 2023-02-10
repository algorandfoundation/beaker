import pyteal as pt
import pytest

from beaker import Application, Authorize
from beaker.application import _default_argument_from_resolver

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_external_read_only():
    app = Application("")

    @app.external(read_only=True)
    def handleable() -> pt.Expr:
        return pt.Approve()

    assert isinstance(handleable, pt.ABIReturnSubroutine)
    assert "handleable" in app.abi_methods

    assert app.build().dictify()["hints"]["handleable"].get("read_only") is True


def test_authorize_only():
    auth_only = Authorize.only(pt.Global.creator_address())

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only.subroutine.implementation(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_external_authorize():
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


def test_authorize_holds_token():

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


def test_external_authorize_holds_token():
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


def test_authorize_opted_in():

    with pytest.raises(pt.TealTypeError):
        Authorize.holds_token(pt.Bytes("abc"))

    app_id = pt.Int(123)
    auth_opted_in = Authorize.opted_in(app_id)

    expr = pt.App.optedIn(pt.Txn.sender(), app_id)

    expected = expr.__teal__(options)
    actual = auth_opted_in.subroutine.implementation(pt.Txn.sender()).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected


def test_external_authorize_opted_in():
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


def test_authorize_bare_handler():
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
        def thing(a, b):
            return pt.Int(1)

        @app.external(authorize=thing)
        def other_thing():
            pass

    with pytest.raises(pt.TealTypeError):

        @pt.Subroutine(pt.TealType.bytes)
        def thing(x):
            return pt.Bytes("fail")

        @app.external(authorize=thing)
        def other_other_thing():
            pass


def test_named_tuple():
    class Order(pt.abi.NamedTuple):
        item: pt.abi.Field[pt.abi.String]
        count: pt.abi.Field[pt.abi.Uint64]

    app = Application("")

    @app.external
    def thing(o: Order) -> pt.Expr:
        return pt.Approve()

    hints = app.build().hints
    assert hints is not None
    thing_hints = hints.get("thing")
    assert thing_hints is not None
    assert thing_hints.structs is not None
    o_hint = thing_hints.structs.get("o")
    assert o_hint == {
        "name": "Order",
        "elements": [["item", "string"], ["count", "uint64"]],
    }


@pytest.mark.parametrize(
    "decorator_name",
    ["create", "no_op", "delete", "update", "opt_in", "close_out"],
)
def test_decorators_with_bare_signature(decorator_name: str):
    app = Application("")
    decorator = getattr(app, decorator_name)

    @decorator
    def test() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(test, pt.SubroutineFnWrapper)
    assert "test" in app.bare_methods


def test_bare_clear_state():
    app = Application("clear_state")

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(clear_state, pt.SubroutineFnWrapper)
    assert "clear_state" not in app.bare_methods
    assert app._clear_state_method is clear_state


def test_bare_external():
    app = Application("bare_external")

    @app.external(bare=True, method_config=pt.MethodConfig(no_op=pt.CallConfig.ALL))
    def external() -> pt.Expr:
        return pt.Approve()

    assert isinstance(external, pt.SubroutineFnWrapper)
    assert "external" in app.bare_methods


@pytest.mark.parametrize(
    "config", [pt.CallConfig.CREATE, pt.CallConfig.CALL, pt.CallConfig.ALL]
)
def test_external_method_config(config: pt.CallConfig):
    app = Application("")

    @app.external(method_config=pt.MethodConfig(no_op=config))
    def external() -> pt.Expr:
        return pt.Approve()

    app_spec = app.build()
    assert app_spec.hints["external"].config.no_op == config


def test_account_state_resolvable():
    from beaker.state import AccountStateValue

    x = AccountStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = _default_argument_from_resolver(x)
    assert r["source"] == "local-state"


def test_reserved_account_state_resolvable():
    from beaker.state import ReservedAccountStateValue

    x = ReservedAccountStateValue(pt.TealType.uint64, max_keys=1)
    r = _default_argument_from_resolver(x[pt.Bytes("x")])
    assert r["source"] == "local-state"


def test_application_state_resolvable():
    from beaker.state import ApplicationStateValue

    x = ApplicationStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = _default_argument_from_resolver(x)
    assert r["source"] == "global-state"


def test_reserved_application_state_resolvable():
    from beaker.state import (
        ReservedApplicationStateValue,
    )

    x = ReservedApplicationStateValue(pt.TealType.uint64, max_keys=1)
    r = _default_argument_from_resolver(x[pt.Bytes("x")])
    assert r["source"] == "global-state"


def test_abi_method_resolvable():
    app = Application("")

    @app.external(read_only=True)
    def x():
        return pt.Assert(pt.Int(1))

    assert isinstance(x, pt.ABIReturnSubroutine)
    r = _default_argument_from_resolver(x)
    assert r["source"] == "abi-method"


def test_bytes_constant_resolvable():
    r = _default_argument_from_resolver(pt.Bytes("1"))
    assert r["source"] == "constant"


def test_int_constant_resolvable():
    r = _default_argument_from_resolver(pt.Int(1))
    assert r["source"] == "constant"
