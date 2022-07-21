from dataclasses import dataclass, field, replace
from enum import Enum
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
from beaker.state import (
    ApplicationStateValue,
    AccountStateValue,
)
from beaker.model import Model

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"


@dataclass
class HandlerConfig:
    """HandlerConfig contains all the extra bits of info about a given ABI method"""

    method_spec: Method = field(kw_only=True, default=None)
    subroutine: Subroutine = field(kw_only=True, default=None)
    bare_method: BareCallActions = field(kw_only=True, default=None)

    referenced_self: bool = field(kw_only=True, default=False)
    models: dict[str, Model] = field(kw_only=True, default=None)

    resolvable: "ResolvableArguments" = field(kw_only=True, default=None)
    method_config: MethodConfig = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)

    def hints(self) -> "MethodHints":
        mh = MethodHints(read_only=self.read_only)

        if self.resolvable is not None:
            mh.resolvable = self.resolvable.__dict__

        if self.models is not None:
            mh.models = {
                arg_name: {
                    "name": model_spec.__name__,
                    "elements": list(model_spec.__annotations__.keys()),
                }
                for arg_name, model_spec in self.models.items()
            }

        return mh


def get_handler_config(fn: HandlerFunc) -> HandlerConfig:
    if hasattr(fn, _handler_config_attr):
        return cast(HandlerConfig, getattr(fn, _handler_config_attr))
    return HandlerConfig()


def set_handler_config(fn: HandlerFunc, **kwargs):
    handler_config = get_handler_config(fn)
    setattr(fn, _handler_config_attr, replace(handler_config, **kwargs))


@dataclass
class MethodHints:
    """MethodHints provides some hints to the caller"""

    resolvable: dict[str, dict[str, Any]] = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)
    models: dict[str, dict[str, str | list[str]]] = field(kw_only=True, default=None)

    def dictify(self) -> dict[str, Any]:
        d = {}
        if self.read_only:
            d["read_only"] = True
        if self.models is not None:
            d["models"] = self.models
        if self.resolvable is not None:
            d["resolvable"] = self.resolvable
        return d


class ResolvableTypes(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


class ResolvableArguments:
    """ResolvableArguments is a container for any arguments that may be resolved prior to calling some target method"""

    def __init__(
        self,
        **kwargs: dict[
            str, AccountStateValue | ApplicationStateValue | HandlerFunc | str | int
        ],
    ):

        resolvable_args = {}
        for arg_name, arg_resolver in kwargs.items():
            match arg_resolver:
                case AccountStateValue():
                    resolvable_args[arg_name] = {
                        ResolvableTypes.LocalState: arg_resolver.str_key()
                    }
                case ApplicationStateValue():
                    resolvable_args[arg_name] = {
                        ResolvableTypes.GlobalState: arg_resolver.str_key()
                    }
                case str() | int():
                    resolvable_args[arg_name] = {ResolvableTypes.Constant: arg_resolver}
                case _:
                    hc = get_handler_config(arg_resolver)
                    if hc.method_spec is None or not hc.read_only:
                        raise Exception(
                            "Expected str, int, ApplicationStateValue, AccountStateValue or read only ABI method"
                        )
                    resolvable_args[arg_name] = {
                        ResolvableTypes.ABIMethod: hc.method_spec.dictify()
                    }

        self.__dict__.update(**resolvable_args)

    def check_arguments(self, sig: Signature):
        for k in self.__dict__.keys():
            if k not in sig.parameters:
                raise Exception(
                    f"The ResolvableArgument field {k} not present in function signature"
                )


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
            params[k] = v.replace(annotation=cls().annotation_type())
            annotations[k] = cls().annotation_type()
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
) -> HandlerFunc:
    """handler is the primary way to expose an ABI method for an application

    :param fn: The function being wrapped
    :param authorize: a subroutine with input of ``Txn.sender()`` and output uint64 interpreted as allowed if the output>0.
    :param method_config:  A subroutine that should take a single argument (Txn.sender()) and evaluate to 1/0 depending on the app call transaction sender (TODO: link to py sdk docs)
    :param read_only: Mark a method as callable with no fee (using Dryrun, place holder until arc22 is merged).A
    :param resolvable: **Experimental** Provides a means to resolve some required input to the caller.
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

        set_handler_config(fn, method_spec=ABIReturnSubroutine(fn).method_spec())

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


def create(fn: HandlerFunc):
    return bare_handler(no_op=CallConfig.CREATE)(fn)


def delete(fn: HandlerFunc):
    return bare_handler(delete_application=CallConfig.CALL)(fn)


def update(fn: HandlerFunc):
    return bare_handler(update_application=CallConfig.CALL)(fn)


def opt_in(fn: HandlerFunc):
    return bare_handler(opt_in=CallConfig.CALL)(fn)


def clear_state(fn: HandlerFunc):
    return bare_handler(clear_state=CallConfig.CALL)(fn)


def close_out(fn: HandlerFunc):
    return bare_handler(close_out=CallConfig.CALL)(fn)


def no_op(fn: HandlerFunc):
    return bare_handler(no_op=CallConfig.CALL)(fn)
