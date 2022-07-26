from dataclasses import dataclass, field, replace
from enum import Enum
from functools import wraps
from inspect import get_annotations, signature, Signature
from typing import Optional, Callable, Final, cast, Any
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
from beaker.struct import Struct

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"


@dataclass
class HandlerConfig:
    """HandlerConfig contains all the extra bits of info about a given ABI method"""

    method_spec: Optional[Method] = field(kw_only=True, default=None)
    subroutine: Optional[Subroutine] = field(kw_only=True, default=None)
    bare_method: Optional[BareCallActions] = field(kw_only=True, default=None)

    referenced_self: bool = field(kw_only=True, default=False)
    structs: Optional[dict[str, Struct]] = field(kw_only=True, default=None)

    resolvable: Optional["ResolvableArguments"] = field(kw_only=True, default=None)
    method_config: Optional[MethodConfig] = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)

    def hints(self) -> "MethodHints":
        mh = MethodHints(read_only=self.read_only)

        if self.resolvable is not None:
            mh.resolvable = self.resolvable.__dict__

        if self.structs is not None:
            mh.structs = {
                arg_name: {
                    "name": model_spec.__name__,  # type: ignore[attr-defined]
                    "elements": list(model_spec.__annotations__.keys()),
                }
                for arg_name, model_spec in self.structs.items()
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
    """MethodHints provides hints to the caller about how to call the method"""

    #: hints to resolve a given argument, see :ref:`resolvable <resolvable>` for more
    resolvable: Optional[dict[str, dict[str, Any]]] = field(kw_only=True, default=None)
    #: hint to indicate this method can be called through Dryrun
    read_only: bool = field(kw_only=True, default=False)
    #: hint to provide names for tuple argument indices, see :doc:`structs` for more
    structs: Optional[dict[str, dict[str, str | list[str]]]] = field(
        kw_only=True, default=None
    )

    def dictify(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.read_only:
            d["read_only"] = True
        if self.structs is not None:
            d["structs"] = self.structs
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
                    hc = get_handler_config(cast(HandlerFunc, arg_resolver))
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
        """require that the sender of the app call match exactly the address passed"""

        if addr.type_of() != TealType.bytes:
            raise TealTypeError(addr.type_of(), TealType.bytes)

        @Subroutine(TealType.uint64, name="auth_only")
        def _impl(sender: Expr):
            return sender == addr

        return _impl

    @staticmethod
    def holds_token(asset_id: Expr):
        """require that the sender of the app call holds >0 of the asset id passed"""

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
        """require that the sender of the app call has already opted-in to a given app id"""

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


def _replace_structs(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()

    replaced = {}
    annotations = get_annotations(fn)
    for k, v in params.items():
        cls = v.annotation
        if hasattr(v.annotation, "__origin__"):
            # Generic type, not a Struct
            continue

        if issubclass(cls, Struct):
            params[k] = v.replace(annotation=cls().annotation_type())
            annotations[k] = cls().annotation_type()
            replaced[k] = cls

    if len(replaced.keys()) > 0:
        set_handler_config(fn, structs=replaced)

    newsig = sig.replace(parameters=list(params.values()))
    fn.__signature__ = newsig  # type: ignore[attr-defined]
    fn.__annotations__ = annotations

    return fn


def _remove_self(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()

    if "self" in params:
        del params["self"]
        # Flag that this method did have a `self` argument
        set_handler_config(fn, referenced_self=True)
    newsig = sig.replace(parameters=list(params.values()))
    fn.__signature__ = newsig  # type: ignore[attr-defined]

    return fn


def internal(return_type: TealType):
    """creates a subroutine to be called by logic internally

    Args:
        return_type: The type this method's returned Expression should evaluate to
    Returns:
        The wrapped subroutine
    """

    def _impl(fn: HandlerFunc):
        hc = get_handler_config(fn)

        hc.subroutine = Subroutine(return_type, name=fn.__name__)
        if "self" in signature(fn).parameters:
            hc.referenced_self = True

        set_handler_config(fn, **hc.__dict__)
        return fn

    return _impl


def external(
    fn: HandlerFunc = None,
    /,
    *,
    authorize: SubroutineFnWrapper = None,
    method_config: MethodConfig = None,
    read_only: bool = False,
    resolvable: ResolvableArguments = None,
) -> HandlerFunc:

    """
    Add the method decorated to be handled as an ABI method for the Application

    Args:
        fn: The function being wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64 interpreted as allowed if the output>0.
        method_config:  A subroutine that should take a single argument (Txn.sender()) and evaluate to 1/0 depending on the app call transaction sender.
        read_only: Mark a method as callable with no fee (using Dryrun, place holder until arc22 is merged).
        resolvable: **Experimental** Provides a means to resolve some required input to the caller.

    Returns:
        The original method with additional elements set in its  :code:`__handler_config__` attribute
    """

    def _impl(fn: HandlerFunc):
        fn = _remove_self(fn)
        fn = _replace_structs(fn)

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


def bare_external(
    no_op: CallConfig = None,
    opt_in: CallConfig = None,
    clear_state: CallConfig = None,
    delete_application: CallConfig = None,
    update_application: CallConfig = None,
    close_out: CallConfig = None,
) -> Callable[..., HandlerFunc]:
    """Add method to be handled by specific bare :code:`OnComplete` actions.

    Args:
        no_op: CallConfig to handle a `NoOp`
        opt_in: CallConfig to handle an `OptIn`
        clear_state: CallConfig to handle a `ClearState`
        delete_application: CallConfig to handle a `DeleteApplication`
        update_application: CallConfig to handle a `UpdateApplication`
        close_out: CallConfig to handle a `CloseOut`

    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`

    """

    def _impl(fun: HandlerFunc) -> HandlerFunc:
        fun = _remove_self(fun)
        fn = Subroutine(TealType.none)(fun)
        bca = BareCallActions(
            no_op=OnCompleteAction(action=fn, call_config=no_op)
            if no_op is not None
            else OnCompleteAction.never(),
            delete_application=OnCompleteAction(
                action=fn, call_config=delete_application
            )
            if delete_application is not None
            else OnCompleteAction.never(),
            update_application=OnCompleteAction(
                action=fn, call_config=update_application
            )
            if update_application is not None
            else OnCompleteAction.never(),
            opt_in=OnCompleteAction(action=fn, call_config=opt_in)
            if opt_in is not None
            else OnCompleteAction.never(),
            close_out=OnCompleteAction(action=fn, call_config=close_out)
            if close_out is not None
            else OnCompleteAction.never(),
            clear_state=OnCompleteAction(action=fn, call_config=clear_state)
            if clear_state is not None
            else OnCompleteAction.never(),
        )

        set_handler_config(fun, bare_method=bca)

        return fun

    return _impl


def create(fn: HandlerFunc):
    """set method to be handled by a bare :code:`NoOp` call and ApplicationId == 0

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """
    return bare_external(no_op=CallConfig.CREATE)(fn)


def delete(fn: HandlerFunc):
    """set method to be handled by a bare :code:`DeleteApplication` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """
    return bare_external(delete_application=CallConfig.CALL)(fn)


def update(fn: HandlerFunc):
    """set method to be handled by a bare :code:`UpdateApplication` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """
    return bare_external(update_application=CallConfig.CALL)(fn)


def opt_in(fn: HandlerFunc):
    """set method to be handled by a bare :code:`OptIn` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """
    return bare_external(opt_in=CallConfig.CALL)(fn)


def clear_state(fn: HandlerFunc):
    """set method to be handled by a bare :code:`ClearState` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """

    return bare_external(clear_state=CallConfig.CALL)(fn)


def close_out(fn: HandlerFunc):
    """set method to be handled by a bare :code:`CloseOut` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """

    return bare_external(close_out=CallConfig.CALL)(fn)


def no_op(fn: HandlerFunc):
    """set method to be handled by a bare :code:`NoOp` call

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set in its `__handler_config__`
    """
    return bare_external(no_op=CallConfig.CALL)(fn)
