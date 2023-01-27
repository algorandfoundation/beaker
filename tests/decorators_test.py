import pyteal as pt
import pytest

from beaker import Application
from beaker.decorators import DefaultArgument, Authorize

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_external_read_only():
    app = Application()

    @app.external(read_only=True)
    def handleable() -> pt.Expr:
        return pt.Approve()

    assert isinstance(handleable, pt.ABIReturnSubroutine)
    assert "handleable" in app.abi_methods

    app.compile()

    assert app.application_spec()["hints"]["handleable"].get("read_only") is True


def test_authorize_only():
    auth_only = Authorize.only(pt.Global.creator_address())

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only.subroutine.implementation(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_external_authorize():
    app = Application()
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
    app = Application()
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
    app = Application()
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
    app = Application()
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

    app = Application()

    @app.external
    def thing(o: Order) -> pt.Expr:
        return pt.Approve()

    app.compile()
    hints = app.hints
    assert hints is not None
    thing_hints = hints.get("thing")
    assert thing_hints is not None
    assert thing_hints.structs is not None
    o_hint = thing_hints.structs.get("o")
    assert o_hint == {
        "name": "Order",
        "elements": [("item", "string"), ("count", "uint64")],
    }


def test_bare():
    app = Application(implement_default_create=False)

    @app.create
    def create() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(create, pt.SubroutineFnWrapper)
    assert "create" in app.bare_methods

    app.deregister_bare_method(create)

    @app.no_op
    def no_op() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(no_op, pt.SubroutineFnWrapper)
    assert "no_op" in app.bare_methods

    @app.delete
    def delete() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(delete, pt.SubroutineFnWrapper)
    assert "delete" in app.bare_methods

    @app.update
    def update() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(update, pt.SubroutineFnWrapper)
    assert "update" in app.bare_methods

    @app.opt_in
    def opt_in() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(opt_in, pt.SubroutineFnWrapper)
    assert "opt_in" in app.bare_methods

    @app.close_out
    def close_out() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(close_out, pt.SubroutineFnWrapper)
    assert "close_out" in app.bare_methods

    @app.clear_state
    def clear_state() -> pt.Expr:
        return pt.Assert(pt.Int(1))

    assert isinstance(clear_state, pt.SubroutineFnWrapper)
    assert "clear_state" in app.bare_methods

    @app.external(bare=True, method_config={"no_op": pt.CallConfig.ALL}, override=True)
    def external() -> pt.Expr:
        return pt.Approve()

    assert isinstance(external, pt.SubroutineFnWrapper)
    assert "external" in app.bare_methods


def test_account_state_resolvable():
    from beaker.state import AccountStateValue

    x = AccountStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = DefaultArgument(x)
    assert r.resolvable_class == "local-state"


def test_reserved_account_state_resolvable():
    from beaker.state import ReservedAccountStateValue

    x = ReservedAccountStateValue(pt.TealType.uint64, max_keys=1)
    r = DefaultArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "local-state"


def test_application_state_resolvable():
    from beaker.state import ApplicationStateValue

    x = ApplicationStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = DefaultArgument(x)
    assert r.resolvable_class == "global-state"


def test_reserved_application_state_resolvable():
    from beaker.state import (
        ReservedApplicationStateValue,
    )

    x = ReservedApplicationStateValue(pt.TealType.uint64, max_keys=1)
    r = DefaultArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "global-state"


def test_abi_method_resolvable():
    app = Application()

    @app.external(read_only=True)
    def x():
        return pt.Assert(pt.Int(1))

    assert isinstance(x, pt.ABIReturnSubroutine)
    r = DefaultArgument(x)
    assert r.resolvable_class == "abi-method"


def test_bytes_constant_resolvable():
    r = DefaultArgument(pt.Bytes("1"))
    assert r.resolvable_class == "constant"


def test_int_constant_resolvable():
    r = DefaultArgument(pt.Int(1))
    assert r.resolvable_class == "constant"
