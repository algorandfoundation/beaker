import pytest
import pyteal as pt

from .decorators import (
    external,
    get_handler_config,
    DefaultArgument,
    Authorize,
    create,
    clear_state,
    close_out,
    delete,
    update,
    no_op,
    opt_in,
)

options = pt.CompileOptions(mode=pt.Mode.Application, version=pt.MAX_TEAL_VERSION)


def test_handler_config():
    @external
    def handleable():
        pass

    hc = get_handler_config(handleable)

    assert hc.method_spec is not None, "Expected abi method to be created"
    meth = hc.method_spec
    assert len(meth.args) == 0, "Expected no args"
    assert meth.name == "handleable", "Expected name to match"

    config_dict = hc.__dict__
    del config_dict["method_spec"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @external(read_only=True)
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.method_spec is not None, "Expected abi method to be created"
    del config_dict["method_spec"]

    assert hc.read_only is True, "Expected read_only to be true"
    del config_dict["read_only"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @external(authorize=Authorize.only(pt.Global.creator_address()))
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.method_spec is not None, "Expected abi method to be created"
    del config_dict["method_spec"]
    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"

    ###

    @external(method_config=pt.MethodConfig(opt_in=pt.CallConfig.CALL))
    def handleable():
        pass

    hc = get_handler_config(handleable)

    config_dict = hc.__dict__

    assert hc.method_spec is not None, "Expected abi method to be created"
    del config_dict["method_spec"]

    assert hc.method_config is not None, "Expected method config to be set"
    assert (
        hc.method_config.opt_in == pt.CallConfig.CALL
    ), "Expected method config opt in to be set to call"
    del config_dict["method_config"]

    for k, v in config_dict.items():
        assert v is None or v is False, f"Expected {k} to be unset"


def test_authorize():

    cmt = "unauthorized"

    auth_only = Authorize.only(pt.Global.creator_address())

    expr = pt.Txn.sender() == pt.Global.creator_address()
    expected = expr.__teal__(options)
    actual = auth_only.subroutine.implementation(pt.Txn.sender()).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    @external(authorize=auth_only)
    def creator_only():
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = creator_only().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

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

    @external(authorize=auth_holds_token)
    def holds_token_only():
        return pt.Approve()

    expr = pt.Seq(
        pt.Assert(auth_holds_token(pt.Txn.sender()), comment=cmt), pt.Approve()
    )

    expected = expr.__teal__(options)
    actual = holds_token_only().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        Authorize.holds_token(pt.Bytes("abc"))

    app_id = pt.Int(123)
    auth_opted_in = Authorize.opted_in(app_id)

    expr = pt.App.optedIn(pt.Txn.sender(), app_id)

    expected = expr.__teal__(options)
    actual = auth_opted_in.subroutine.implementation(pt.Txn.sender()).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    @external(authorize=auth_opted_in)
    def opted_in_only():
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_opted_in(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = opted_in_only().__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    # Bare handler

    @delete(authorize=auth_only)
    def deleter():
        return pt.Approve()

    expr = pt.Seq(pt.Assert(auth_only(pt.Txn.sender()), comment=cmt), pt.Approve())

    expected = expr.__teal__(options)
    actual = deleter().__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    with pytest.raises(pt.TealTypeError):
        Authorize.opted_in(pt.Bytes("abc"))

    with pytest.raises(pt.TealInputError):

        @pt.Subroutine(pt.TealType.uint64)
        def thing(a, b):
            return pt.Int(1)

        @external(authorize=thing)
        def other_thing():
            pass

    with pytest.raises(pt.TealTypeError):

        @pt.Subroutine(pt.TealType.bytes)
        def thing(x):
            return pt.Bytes("fail")

        @external(authorize=thing)
        def other_other_thing():
            pass


def test_named_tuple():
    class Order(pt.abi.NamedTuple):
        item: pt.abi.Field[pt.abi.String]
        count: pt.abi.Field[pt.abi.Uint64]

    @external
    def thing(o: Order):
        pass

    hc = get_handler_config(thing)
    assert hc.structs["o"] is Order


def test_bare():
    @create
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.no_op.action.subroutine.implementation == impl

    @no_op
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.no_op.action.subroutine.implementation == impl

    @delete
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.delete_application.action.subroutine.implementation == impl

    @update
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.update_application.action.subroutine.implementation == impl

    @opt_in
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.opt_in.action.subroutine.implementation == impl

    @close_out
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.close_out.action.subroutine.implementation == impl

    @clear_state
    def impl():
        return pt.Assert(pt.Int(1))

    hc = get_handler_config(impl)
    assert hc.bare_method.clear_state.action.subroutine.implementation == impl


def test_resolvable():
    from .state import (
        AccountStateValue,
        ApplicationStateValue,
        DynamicAccountStateValue,
        DynamicApplicationStateValue,
    )

    x = AccountStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = DefaultArgument(x)
    assert r.resolvable_class == "local-state"

    x = DynamicAccountStateValue(pt.TealType.uint64, max_keys=1)
    r = DefaultArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "local-state"

    x = ApplicationStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = DefaultArgument(x)
    assert r.resolvable_class == "global-state"

    x = DynamicApplicationStateValue(pt.TealType.uint64, max_keys=1)
    r = DefaultArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "global-state"

    @external(read_only=True)
    def x():
        return pt.Assert(pt.Int(1))

    r = DefaultArgument(x)
    assert r.resolvable_class == "abi-method"

    r = DefaultArgument(pt.Bytes("1"))
    assert r.resolvable_class == "constant"

    r = DefaultArgument(pt.Int(1))
    assert r.resolvable_class == "constant"
