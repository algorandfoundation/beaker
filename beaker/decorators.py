import functools
from inspect import signature
from typing import Any, Callable, Final

from pyteal import (
    ABIReturnSubroutine,
    And,
    App,
    Assert,
    AssetHolding,
    BareCallActions,
    BitLen,
    CallConfig,
    Concat,
    Expr,
    Int,
    MethodConfig,
    OnCompleteAction,
    Seq,
    Subroutine,
    SubroutineFnWrapper,
    TealInputError,
    TealType,
    Txn,
    TxnField,
)

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"
_abi_method: Final[str] = "_abi_method"
_bare_method: Final[str] = "_bare_method"


def get_handler_config(
    fn: HandlerFunc | ABIReturnSubroutine | OnCompleteAction,
) -> dict[str, Any]:
    handler_config = {}
    if hasattr(fn, _handler_config_attr):
        handler_config = getattr(fn, _handler_config_attr)

    return handler_config


def add_handler_config(
    fn: HandlerFunc | ABIReturnSubroutine | OnCompleteAction, key: str, val: Any
):
    handler_config = get_handler_config(fn)
    handler_config[key] = val
    setattr(fn, _handler_config_attr, handler_config)


class Authorize:
    """Authorize contains methods that may be used as values to the `authorize` keyword of the `handle` decorator"""

    @staticmethod
    def only(addr: Expr):
        """only requires that the sender of the app call being evaluated match exactly the address passed"""

        @Subroutine(TealType.uint64, name="auth_only")
        def _impl(sender: Expr):
            return sender == addr

        return _impl

    @staticmethod
    def holds_token(asset_id: Expr):
        """holds_token ensures that the sender of the app call being evaluated holds >0 of the asset id passed"""

        @Subroutine(TealType.uint64, name="auth_holds_token")
        def _impl(sender: Expr):
            return Seq(
                bal := AssetHolding.balance(sender, asset_id),
                And(bal.hasValue(), bal.value() > Int(0)),
            )

        return _impl

    @staticmethod
    def opted_in(app_id: Expr):
        """opted_in ensures that the sender of the app call being evaluated has already opted-in to a given app id"""

        @Subroutine(TealType.uint64, name="auth_opted_in")
        def _impl(sender: Expr):
            return App.optedIn(sender, app_id)

        return _impl


def _authorize(allowed: SubroutineFnWrapper):
    if allowed.type_of() != TealType.uint64:
        raise TealInputError(
            f"Expected authorize method to return TealType.uint64, got {allowed.type_of()}"
        )

    def _decorate(fn: HandlerFunc):
        def _impl(*args, **kwargs):
            return Seq(Assert(allowed(Txn.sender())), fn(*args, **kwargs))

        _impl.__name__ = fn.__name__
        _impl.__annotations__ = fn.__annotations__
        _impl.__signature__ = signature(fn)
        _impl.__doc__ = fn.__doc__

        return _impl

    return _decorate


def _readonly(fn: HandlerFunc):
    # add_handler_config(fn, "read_only", True)
    return fn


def _on_complete(mc: MethodConfig):
    def _impl(fn: HandlerFunc):
        add_handler_config(fn, "method_config", mc)
        return fn

    return _impl


def _remove_self(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()
    if "self" in params:
        del params["self"]
    newsig = sig.replace(parameters=params.values())
    fn.__signature__ = newsig
    return fn


def bare_handler(
    no_op: CallConfig = None,
    opt_in: CallConfig = None,
    clear_state: CallConfig = None,
    delete_application: CallConfig = None,
    update_application: CallConfig = None,
    close_out: CallConfig = None,
):
    def _impl(fun: HandlerFunc) -> OnCompleteAction:

        fun = _remove_self(fun)

        fn = Subroutine(TealType.none)(fun)

        bca = BareCallActions(
            no_op=OnCompleteAction(action=fn, call_config=no_op)
            if no_op is not None
            else None,
            delete_application=OnCompleteAction(
                action=fn, call_config=delete_application
            )
            if delete_application is not None
            else None,
            update_application=OnCompleteAction(
                action=fn, call_config=update_application
            )
            if update_application is not None
            else None,
            opt_in=OnCompleteAction(action=fn, call_config=opt_in)
            if opt_in is not None
            else None,
            close_out=OnCompleteAction(action=fn, call_config=close_out)
            if close_out is not None
            else None,
            clear_state=OnCompleteAction(action=fn, call_config=delete_application)
            if clear_state is not None
            else None,
        )

        add_handler_config(fun, _bare_method, bca)

        return fun

    return _impl


def internal(return_type: TealType):
    """internal can be used to wrap a subroutine that is defined inside an application class"""

    def _impl(fn: HandlerFunc):
        return Subroutine(return_type)(fn)

    return _impl


def handler(
    fn: HandlerFunc = None,
    /,
    *,
    authorize: SubroutineFnWrapper = None,
    method_config: MethodConfig = None,
    read_only: bool = False,
):
    """
    handler is the primary way to expose an ABI method for an application
    it may take a number of arguments:

    Args:

        authorize: A subroutine that should evaluate to 1/0 depending on the app call transaction sender
        method_config: accepts a MethodConfig object to define how the app call should be routed given OnComplete and whether or not the call is a create
        read_only: adds read_only flag to abi (eventually, currently it does nothing)
    """

    def _impl(fn: HandlerFunc):
        fn = _remove_self(fn)

        if authorize is not None:
            fn = _authorize(authorize)(fn)
        if method_config is not None:
            fn = _on_complete(method_config)(fn)
        if read_only:
            fn = _readonly(fn)

        add_handler_config(fn, _abi_method, ABIReturnSubroutine(fn))

        return fn

    if fn is None:
        return _impl

    return _impl(fn)
