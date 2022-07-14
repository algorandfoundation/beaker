from dataclasses import dataclass, field, replace
from functools import wraps
from inspect import get_annotations, signature, Signature
from typing import Callable, Final, cast, Any
from algosdk.abi import Method
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
    TealTypeError,
    Txn,
)

from beaker.model import Model

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"


class ResolvableArguments:
    """ResolvableArguments is a container for any arguments that may be resolved prior to calling some target method"""

    def __init__(
        self,
        **kwargs: dict[str, ABIReturnSubroutine | HandlerFunc],
    ):

        resolvable_args = {}
        for arg_name, arg_resolver in kwargs.items():
            if not isinstance(arg_resolver, ABIReturnSubroutine):
                # Assume its a handler func and try to get the config
                hc = get_handler_config(arg_resolver)
                if hc.abi_method is None:
                    raise TealTypeError(arg_resolver, ABIReturnSubroutine)

            resolvable_args[arg_name] = hc.abi_method

        self.__dict__.update(**resolvable_args)

    def check_arguments(self, sig: Signature):
        for k in self.__dict__.keys():
            if k not in sig.parameters:
                raise Exception(
                    f"The ResolvableArgument field {k} not present in function signature"
                )


@dataclass
class MethodHints:
    """MethodHints provides some hints to the caller"""

    resolvable: dict[str, Method] = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)
    models: dict[str, list[str]] = field(kw_only=True, default=None)

    def dictify(self) -> dict[str, Any]:
        d = {"resolvable": {}, "read_only": self.read_only, "models": self.models}

        if self.resolvable is not None:
            d["resolvable"] = {k: v.dictify() for k, v in self.resolvable.items()}

        return d


@dataclass
class HandlerConfig:
    """HandlerConfig contains all the extra bits of info about a given ABI method"""

    abi_method: bool = field(kw_only=True, default=False)
    method_config: MethodConfig = field(kw_only=True, default=None)
    bare_method: BareCallActions = field(kw_only=True, default=None)
    referenced_self: bool = field(kw_only=True, default=False)
    read_only: bool = field(kw_only=True, default=False)
    subroutine: Subroutine = field(kw_only=True, default=None)
    resolvable: ResolvableArguments = field(kw_only=True, default=None)
    models: dict[str, Model] = field(kw_only=True, default=None)

    def hints(self) -> MethodHints:
        mh = MethodHints(read_only=self.read_only)

        if self.resolvable is not None:
            resolvable = {}
            for arg_name, ra in self.resolvable.__dict__.items():
                if not isinstance(ra, ABIReturnSubroutine):
                    raise TealTypeError(ra, ABIReturnSubroutine)

                resolvable[arg_name] = ra.method_spec()

            mh.resolvable = resolvable

        if self.models is not None:
            models = {}
            for arg_name, model_spec in self.models.items():
                models[arg_name] = list(model_spec.__annotations__.keys())
            mh.models = models

        return mh


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

        if addr.type_of() != TealType.bytes:
            raise TealTypeError(addr.type_of(), TealType.bytes)

        @Subroutine(TealType.uint64, name="auth_only")
        def _impl(sender: Expr):
            return sender == addr

        return _impl

    @staticmethod
    def holds_token(asset_id: Expr):
        """holds_token ensures that the sender of the app call being evaluated holds >0 of the asset id passed"""

        if asset_id.type_of() != TealType.uint64:
            raise TealTypeError(asset_id.type_of(), TealType.uint64)

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

        if app_id.type_of() != TealType.uint64:
            raise TealTypeError(app_id.type_of(), TealType.uint64)

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
        raise TealTypeError(allowed.type_of(), TealType.uint64)

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


def _replace_models(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()

    replaced = {}
    annotations = get_annotations(fn)
    for k, v in params.items():
        cls = v.annotation
        if hasattr(v.annotation, "__origin__"):
            # Generic type, not a Model
            continue

        if issubclass(cls, Model):
            params[k] = v.replace(annotation=cls().get_type())
            annotations[k] = cls().get_type()
            replaced[k] = cls

    if len(replaced.keys()) > 0:
        set_handler_config(fn, models=replaced)

    newsig = sig.replace(parameters=params.values())
    fn.__signature__ = newsig
    fn.__annotations__ = annotations

    return fn


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


def internal(return_type: TealType):
    """internal can be used to wrap a subroutine that is defined inside an application class"""

    def _impl(fn: HandlerFunc):
        hc = get_handler_config(fn)

        hc.subroutine = Subroutine(return_type, name=fn.__name__)
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
    resolvable: ResolvableArguments = None,
):
    """
    handler is the primary way to expose an ABI method for an application
    it may take a number of arguments:

    Args:

        authorize: A subroutine that should evaluate to 1/0 depending on the app call transaction sender
        method_config: accepts a MethodConfig object to define how the app call should be routed given OnComplete and whether or not the call is a create
        read_only: adds read_only flag to abi (eventually, currently it does nothing)
        resolvable: provides hints to a caller at how to resolve some arguments
    """

    def _impl(fn: HandlerFunc):
        fn = _remove_self(fn)
        fn = _replace_models(fn)

        if resolvable is not None:
            resolvable.check_arguments(signature(fn))
            set_handler_config(fn, resolvable=resolvable)
        if authorize is not None:
            fn = _authorize(authorize)(fn)
        if method_config is not None:
            fn = _on_complete(method_config)(fn)
        if read_only:
            fn = _readonly(fn)

        set_handler_config(fn, abi_method=True)

        return fn

    if fn is None:
        return _impl

    return _impl(fn)


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
            clear_state=OnCompleteAction(action=fn, call_config=clear_state)
            if clear_state is not None
            else None,
        )

        set_handler_config(fun, bare_method=bca)

        return fun

    return _impl


class Bare:
    """Bare contains static methods for handling bare application calls, that is app calls with no arguments"""

    @staticmethod
    def create(fn: HandlerFunc):
        return bare_handler(no_op=CallConfig.CREATE)(fn)

    @staticmethod
    def delete(fn: HandlerFunc):
        return bare_handler(delete_application=CallConfig.CALL)(fn)

    @staticmethod
    def update(fn: HandlerFunc):
        return bare_handler(update_application=CallConfig.CALL)(fn)

    @staticmethod
    def opt_in(fn: HandlerFunc):
        return bare_handler(opt_in=CallConfig.CALL)(fn)

    @staticmethod
    def clear_state(fn: HandlerFunc):
        return bare_handler(clear_state=CallConfig.CALL)(fn)

    @staticmethod
    def close_out(fn: HandlerFunc):
        return bare_handler(close_out=CallConfig.CALL)(fn)

    @staticmethod
    def no_op(fn: HandlerFunc):
        return bare_handler(no_op=CallConfig.CALL)(fn)
