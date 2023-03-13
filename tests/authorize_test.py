import pyteal as pt
import pytest

from beaker import Application, Authorize

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_authorize_only() -> None:
    auth_only = Authorize.only(pt.Global.current_application_address())

    expr = pt.Txn.sender() == pt.Global.current_application_address()
    expected = expr.__teal__(options)
    actual = auth_only(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_authorize_creator() -> None:
    auth_only = Authorize.only_creator()

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_external_authorize() -> None:
    app = Application("")
    cmt = "unauthorized"
    auth_only = Authorize.only_creator()

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
    actual = auth_holds_token(pt.Txn.sender()).__teal__(options)

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

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected


def test_authorize_opted_in() -> None:

    with pytest.raises(pt.TealTypeError):
        Authorize.holds_token(pt.Bytes("abc"))

    app_id = pt.Int(123)
    auth_opted_in = Authorize.opted_in(app_id)

    expr = pt.App.optedIn(pt.Txn.sender(), app_id)

    expected = expr.__teal__(options)
    actual = auth_opted_in(pt.Txn.sender()).__teal__(options)

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


def test_authorize_with_sub() -> None:
    @pt.Subroutine(pt.TealType.uint64)
    def my_auth(sender: pt.Expr) -> pt.Expr:
        return sender == pt.Global.caller_app_address()

    app = Application("")

    @app.external(authorize=my_auth)
    def foo() -> pt.Expr:
        return pt.Approve()

    app.build()


def test_authorize_bare_handler() -> None:
    app1 = Application("")
    cmt = "unauthorized"
    auth_only = Authorize.only_creator()

    @app1.delete(bare=True, authorize=auth_only)
    def deleter() -> pt.Expr:
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = deleter.subroutine.implementation().__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        Authorize.opted_in(pt.Bytes("abc"))

    @pt.Subroutine(pt.TealType.uint64)
    def thing1(a: pt.Expr, b: pt.Expr) -> pt.Expr:
        return pt.Int(1)

    app2 = Application("")

    @app2.external(authorize=thing1)
    def other_thing() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(pt.TealInputError):
        app2.build()

    app3 = Application("")

    @pt.Subroutine(pt.TealType.bytes)
    def thing2(x: pt.Expr) -> pt.Expr:
        return pt.Bytes("fail")

    @app3.external(authorize=thing2)
    def other_other_thing() -> pt.Expr:
        return pt.Approve()

    with pytest.raises(pt.TealTypeError):
        app3.build()
