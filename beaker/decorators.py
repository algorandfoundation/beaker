from typing import Any
from dataclasses import dataclass, field, replace
from functools import wraps
from inspect import signature
from typing import Callable, Final, cast

from pyteal import (
    ABIReturnSubroutine,
    And,
    App,
    Assert,
    AssetHolding,
    BareCallActions,
    CallConfig,
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
)

from beaker.application_schema import GlobalStateValue, LocalStateValue

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"


@dataclass
class HandlerConfig:
    abi_method: ABIReturnSubroutine = field(kw_only=True, default=None)
    method_config: MethodConfig = field(kw_only=True, default=None)
    bare_method: BareCallActions = field(kw_only=True, default=None)
    referenced_self: bool = field(kw_only=True, default=False)
    read_only: bool = field(kw_only=True, default=False)
    subroutine: Subroutine = field(kw_only=True, default=None)
    required_args: dict[str, ABIReturnSubroutine] = field(kw_only=True, default=None)

    def hints(self) -> dict[str, Any]:
        hints = {
            "required-args": {},
            "read-only": self.read_only,
        }

        if self.required_args is not None:
            for name, ra in self.required_args.items():
                hints["required-args"][name] = ra.method_spec().dictify()

        return hints


def get_handler_config(fn: HandlerFunc) -> HandlerConfig:
    if hasattr(fn, _handler_config_attr):
        return cast(HandlerConfig, getattr(fn, _handler_config_attr))
    return HandlerConfig()


def set_handler_config(fn: HandlerFunc, **kwargs):
    handler_config = get_handler_config(fn)
    setattr(fn, _handler_config_attr, replace(handler_config, **kwargs))


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
    args = allowed.subroutine.expected_arg_types

    if len(args) != 1 or args[0] is not Expr:
        raise TealInputError(
            "Expected a single expression argument to authorize function"
        )

    if allowed.type_of() != TealType.uint64:
        raise TealInputError(
            f"Expected authorize method to return TealType.uint64, got {allowed.type_of()}"
        )

    def _decorate(fn: HandlerFunc):
        @wraps(fn)
        def _impl(*args, **kwargs):
            return Seq(Assert(allowed(Txn.sender())), fn(*args, **kwargs))

        return _impl

    return _decorate


def _readonly(fn: HandlerFunc):
    set_handler_config(fn, read_only=True)
    return fn


def _on_complete(mc: MethodConfig):
    def _impl(fn: HandlerFunc):
        set_handler_config(fn, method_config=mc)
        return fn

    return _impl


def _remove_self(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()

    if "self" in params:
        del params["self"]
        # Flag that this method did have a `self` argument
        set_handler_config(fn, referenced_self=True)
    newsig = sig.replace(parameters=params.values())
    fn.__signature__ = newsig

    return fn


def required_args(**required_args: ABIReturnSubroutine | HandlerFunc):

    for name, arg in required_args.items():
        if not isinstance(arg, ABIReturnSubroutine):
            hc = get_handler_config(arg)
            if hc.abi_method is None:
                raise Exception(f"Expected ABISubroutine, got {required_args}")

            required_args[name] = hc.abi_method

    def _impl(fn: HandlerFunc):
        set_handler_config(fn, required_args=required_args)
        return fn

    return _impl


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

        set_handler_config(fun, bare_method=bca)

        return fun

    return _impl


def bare_create(fn: HandlerFunc):
    return bare_handler(no_op=CallConfig.CREATE)(fn)


def bare_delete(fn: HandlerFunc):
    return bare_handler(delete_application=CallConfig.CALL)(fn)


def bare_update(fn: HandlerFunc):
    return bare_handler(update_application=CallConfig.CALL)(fn)


def bare_opt_in(fn: HandlerFunc):
    return bare_handler(opt_in=CallConfig.CALL)(fn)


def internal(return_type: TealType):
    """internal can be used to wrap a subroutine that is defined inside an application class"""

    def _impl(fn: HandlerFunc):
        hc = get_handler_config(fn)

        hc.subroutine = Subroutine(return_type)
        if "self" in signature(fn).parameters:
            hc.referenced_self = True

        set_handler_config(fn, **hc.__dict__)
        return fn

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

        set_handler_config(fn, abi_method=ABIReturnSubroutine(fn))

        return fn

    if fn is None:
        return _impl

    return _impl(fn)
