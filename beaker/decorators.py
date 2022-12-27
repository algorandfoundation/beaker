from dataclasses import asdict, dataclass, field, replace, astuple
from enum import Enum
from functools import wraps
from inspect import get_annotations, signature, Parameter
from typing import Optional, Callable, Final, cast, Any, TypeVar
from types import FunctionType
from algosdk.abi import Method
from pyteal import (
    abi,
    ABIReturnSubroutine,
    And,
    Global,
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
    Bytes,
    Txn,
)

from beaker.state import AccountStateValue, ApplicationStateValue

HandlerFunc = Callable[..., Expr]

_handler_config_attr: Final[str] = "__handler_config__"


CheckExpr = Callable[..., Expr]
ABIType = TypeVar("ABIType", bound=abi.BaseType)


DefaultArgumentType = Expr | HandlerFunc | int | bytes | str


class DefaultArgumentClass(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


class DefaultArgument:
    """
    DefaultArgument is a container for any arguments that may
    be resolved prior to calling some target method
    """

    def __init__(
        self,
        resolver: DefaultArgumentType,
    ):
        self.resolver = resolver

        match resolver:

            # Expr types
            case AccountStateValue():
                self.resolvable_class = DefaultArgumentClass.LocalState
            case ApplicationStateValue():
                self.resolvable_class = DefaultArgumentClass.GlobalState
            case Bytes() | Int():
                self.resolvable_class = DefaultArgumentClass.Constant

            # Native types
            case int() | str() | bytes():
                self.resolvable_class = DefaultArgumentClass.Constant

            # FunctionType
            case _:
                # Fall through, if its not got a valid handler config, raise error
                hc = get_handler_config(cast(HandlerFunc, resolver))
                if hc.method_spec is None or not hc.read_only:
                    raise TealTypeError(self.resolver, DefaultArgumentType)

                self.resolvable_class = DefaultArgumentClass.ABIMethod

    def resolve_hint(self) -> Any:
        match self.resolver:
            # Expr types
            case AccountStateValue() | ApplicationStateValue():
                return self.resolver.str_key()
            case Bytes():
                return self.resolver.byte_str.replace('"', "")
            case Int():
                return self.resolver.value
            # Native types
            case int() | bytes() | str():
                return self.resolver

            # FunctionType
            case _:
                # Fall through, if its not got a valid handler config, raise error
                hc = get_handler_config(cast(HandlerFunc, self.resolver))
                if hc.method_spec is None or not hc.read_only:
                    raise TealTypeError(self.resolver, DefaultArgumentType)

                return hc.method_spec.dictify()

    def dictify(self) -> dict[str, Any]:
        return {"source": self.resolvable_class.value, "data": self.resolve_hint()}


@dataclass
class HandlerConfig:
    """HandlerConfig contains all the extra bits of info about a given ABI method"""

    method_spec: Optional[Method] = field(kw_only=True, default=None)
    subroutine: Optional[Subroutine] = field(kw_only=True, default=None)
    bare_method: Optional[BareCallActions] = field(kw_only=True, default=None)

    referenced_self: bool = field(kw_only=True, default=False)
    structs: Optional[dict[str, abi.NamedTuple]] = field(kw_only=True, default=None)

    default_arguments: Optional[dict[str, DefaultArgument]] = field(
        kw_only=True, default=None
    )
    method_config: Optional[MethodConfig] = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)
    internal: bool = field(kw_only=True, default=False)

    def hints(self) -> "MethodHints":
        mh: dict[str, Any] = {"read_only": self.read_only}

        if (
            self.default_arguments is not None
            and len(self.default_arguments.keys()) > 0
        ):
            mh["default_arguments"] = self.default_arguments

        if self.structs is not None:
            structs: dict[str, dict[str, str | list[tuple[str, str]]]] = {}
            for arg_name, model_spec in self.structs.items():
                annos: list[tuple[str, Any]] = list(model_spec.__annotations__.items())
                structs[arg_name] = {
                    "name": str(model_spec.__name__),  # type: ignore[attr-defined]
                    "elements": [
                        (name, str(abi.algosdk_from_annotation(typ.__args__[0])))
                        for name, typ in annos
                    ],
                }

            mh["structs"] = structs

        return MethodHints(**mh)

    def is_create(self) -> bool:
        if self.method_config is None:
            return False

        return any(
            map(
                lambda cc: cc == CallConfig.CREATE or cc == CallConfig.ALL,
                astuple(self.method_config),
            )
        )

    def is_update(self) -> bool:
        return (
            self.method_config is not None
            and self.method_config.update_application != CallConfig.NEVER
        )

    def is_delete(self) -> bool:
        return (
            self.method_config is not None
            and self.method_config.delete_application != CallConfig.NEVER
        )

    def is_opt_in(self) -> bool:
        return (
            self.method_config is not None
            and self.method_config.opt_in != CallConfig.NEVER
        )

    def is_clear_state(self) -> bool:
        return (
            self.method_config is not None
            and self.method_config.clear_state != CallConfig.NEVER
        )

    def is_close_out(self) -> bool:
        return (
            self.method_config is not None
            and self.method_config.close_out != CallConfig.NEVER
        )


def get_handler_config(fn: HandlerFunc) -> HandlerConfig:
    if hasattr(fn, _handler_config_attr):
        return cast(HandlerConfig, getattr(fn, _handler_config_attr))
    return HandlerConfig()


def set_handler_config(fn: HandlerFunc, **kwargs) -> None:  # type: ignore
    handler_config = get_handler_config(fn)
    setattr(fn, _handler_config_attr, replace(handler_config, **kwargs))


@dataclass
class MethodHints:
    """MethodHints provides hints to the caller about how to call the method"""

    #: hint to indicate this method can be called through Dryrun
    read_only: bool = field(kw_only=True, default=False)
    #: hint to provide names for tuple argument indices
    #: method_name=>param_name=>{name:str, elements:[str,str]}
    structs: Optional[dict[str, dict[str, str | list[tuple[str, str]]]]] = field(
        kw_only=True, default=None
    )
    #: defaults
    default_arguments: Optional[dict[str, DefaultArgument]] = field(
        kw_only=True, default=None
    )

    def empty(self) -> bool:
        return (
            self.structs is None
            and self.default_arguments is None
            and not self.read_only
        )

    def dictify(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.read_only:
            d["read_only"] = True
        if self.default_arguments is not None:
            d["default_arguments"] = {
                k: v.dictify() for k, v in self.default_arguments.items()
            }
        if self.structs is not None:
            d["structs"] = self.structs
        return d


class Authorize:
    """
    Authorize contains methods that may be used as values to
    the `authorize` keyword of the `handle` decorator
    """

    @staticmethod
    def only(addr: Expr) -> SubroutineFnWrapper:
        """require that the sender of the app call match exactly the address passed"""

        if addr.type_of() != TealType.bytes:
            raise TealTypeError(addr.type_of(), TealType.bytes)

        @Subroutine(TealType.uint64, name="auth_only")
        def _impl(sender: Expr) -> Expr:
            return sender == addr

        return _impl

    @staticmethod
    def holds_token(asset_id: Expr) -> SubroutineFnWrapper:
        """require that the sender of the app call holds >0 of the asset id passed"""

        if asset_id.type_of() != TealType.uint64:
            raise TealTypeError(asset_id.type_of(), TealType.uint64)

        @Subroutine(TealType.uint64, name="auth_holds_token")
        def _impl(sender: Expr) -> Expr:
            return Seq(
                bal := AssetHolding.balance(sender, asset_id),
                And(bal.hasValue(), bal.value() > Int(0)),
            )

        return _impl

    @staticmethod
    def opted_in(app_id: Expr = Global.current_application_id()) -> SubroutineFnWrapper:
        """require that the sender of the app call has
        already opted-in to a given app id"""

        if app_id.type_of() != TealType.uint64:
            raise TealTypeError(app_id.type_of(), TealType.uint64)

        @Subroutine(TealType.uint64, name="auth_opted_in")
        def _impl(sender: Expr) -> Expr:
            return App.optedIn(sender, app_id)

        return _impl


def _authorize(allowed: SubroutineFnWrapper) -> Callable[..., HandlerFunc]:
    args = allowed.subroutine.expected_arg_types

    if len(args) != 1 or args[0] is not Expr:
        raise TealInputError(
            "Expected a single expression argument to authorize function"
        )

    if allowed.type_of() != TealType.uint64:
        raise TealTypeError(allowed.type_of(), TealType.uint64)

    def _decorate(fn: HandlerFunc) -> HandlerFunc:
        @wraps(fn)
        def _impl(*args, **kwargs) -> Expr:  # type: ignore
            return Seq(
                Assert(allowed(Txn.sender()), comment="unauthorized"),
                fn(*args, **kwargs),
            )

        return _impl

    return _decorate


def _readonly(fn: HandlerFunc) -> HandlerFunc:
    set_handler_config(fn, read_only=True)
    return fn


def _on_complete(mc: MethodConfig) -> Callable[..., HandlerFunc]:
    def _impl(fn: HandlerFunc) -> HandlerFunc:
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

        if issubclass(cls, abi.NamedTuple):
            params[k] = v.replace(annotation=cls().type_spec().annotation_type())
            annotations[k] = cls().type_spec().annotation_type()
            replaced[k] = cls

    if len(replaced.keys()) > 0:
        set_handler_config(fn, structs=replaced)

    newsig = sig.replace(parameters=list(params.values()))
    fn.__signature__ = newsig  # type: ignore[attr-defined]
    fn.__annotations__ = annotations

    return fn


def _capture_defaults(fn: HandlerFunc) -> HandlerFunc:
    sig = signature(fn)
    params = sig.parameters.copy()

    default_args: dict[str, DefaultArgument] = {}

    for k, v in params.items():
        match v.default:
            case Expr() | int() | str() | bytes() | FunctionType():
                default_args[k] = DefaultArgument(v.default)
                params[k] = v.replace(default=Parameter.empty)

    if len(default_args.items()) > 0:
        # Update handler config
        set_handler_config(fn, default_arguments=default_args)

        # Fix function sig/annotations
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]

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


def internal(
    return_type_or_handler: TealType | HandlerFunc,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """creates a subroutine to be called by logic internally

    Args:
        return_type: The type this method's returned Expression should evaluate to
    Returns:
        The wrapped subroutine
    """

    fn: Optional[HandlerFunc] = None
    return_type: Optional[TealType] = None

    if type(return_type_or_handler) is TealType:
        return_type = return_type_or_handler
    else:
        fn = cast(HandlerFunc, return_type_or_handler)

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        set_handler_config(fn, internal=True)
        if return_type is not None:
            set_handler_config(fn, subroutine=Subroutine(return_type, name=fn.__name__))

            # Don't remove self for subroutine, it fails later on in pyteal
            # during call to _validate  with invalid signature
            sig = signature(fn)
            if "self" in sig.parameters:
                set_handler_config(fn, referenced_self=True)

        else:
            fn = _remove_self(fn)
            set_handler_config(fn, method_spec=ABIReturnSubroutine(fn).method_spec())

        return fn

    if fn is not None:
        return _impl(fn)

    return _impl


def external(
    fn: HandlerFunc | None = None,
    /,
    *,
    name: str | None = None,
    authorize: SubroutineFnWrapper | None = None,
    method_config: MethodConfig | None = None,
    read_only: bool = False,
) -> HandlerFunc | Callable[..., HandlerFunc]:

    """
    Add the method decorated to be handled as an ABI method for the Application

    Args:
        fn: The function being wrapped.
        name: Name of ABI method. If not set, name of the python method will be used.
            Useful for method overriding.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
        method_config:  A subroutine that should take a single argument (Txn.sender())
            and evaluate to 1/0 depending on the app call transaction sender.
        read_only: Mark a method as callable with no fee using dryrun or simulate

    Returns:
        The original method with additional elements set in it's
        :code:`__handler_config__` attribute
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        fn = _remove_self(fn)
        fn = _capture_defaults(fn)
        fn = _replace_structs(fn)

        if authorize is not None:
            fn = _authorize(authorize)(fn)
        if method_config is not None:
            fn = _on_complete(method_config)(fn)
        if read_only:
            fn = _readonly(fn)

        set_handler_config(
            fn, method_spec=ABIReturnSubroutine(fn, overriding_name=name).method_spec()
        )

        return fn

    if fn is None:
        return _impl

    return _impl(fn)


def bare_external(
    no_op: CallConfig | None = None,
    opt_in: CallConfig | None = None,
    clear_state: CallConfig | None = None,
    delete_application: CallConfig | None = None,
    update_application: CallConfig | None = None,
    close_out: CallConfig | None = None,
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
        The original method with changes made to its signature and attributes set
        in it's :code:`__handler_config__`

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


def is_bare(fn: HandlerFunc) -> bool:
    sig = signature(fn)
    return len(sig.parameters) == 0 or (
        len(sig.parameters) == 1 and "self" in sig.parameters
    )


def create(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    method_config: Optional[MethodConfig] | None = None,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with its :code:`OnComplete`
        set to :code:`NoOp` call and ApplicationId == 0

    Args:
        fn: The method to be wrapped.
    Returns:
        The original method with changes made to its signature and attributes set
        in it's `__handler_config__`
    """

    mconfig = (
        {"no_op": CallConfig.CREATE} if method_config is None else asdict(method_config)
    )

    if not all(
        [cc == CallConfig.CREATE or cc == CallConfig.ALL for cc in mconfig.values()]
    ):
        raise TealInputError(
            "method_config for create may not have non create call configs"
        )

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(**mconfig)(fn)
        else:
            return external(method_config=MethodConfig(**mconfig), authorize=authorize)(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def delete(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
        :code:`OnComplete` set to :code:`DeleteApplication` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and attributes
            set in its :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(delete_application=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(delete_application=CallConfig.CALL),
                authorize=authorize,
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def update(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
        :code:`OnComplete` set to :code:`UpdateApplication` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and attributes
            set in it's :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(update_application=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(update_application=CallConfig.CALL),
                authorize=authorize,
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def opt_in(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
           :code:`OnComplete` set to :code:`OptIn` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output
            uint64 interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and attributes
            set in it's :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(opt_in=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(opt_in=CallConfig.CALL), authorize=authorize
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def clear_state(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it'ws
        :code:`OnComplete` set to :code:`ClearState` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and
            attributes set in it's :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(clear_state=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(clear_state=CallConfig.CALL),
                authorize=authorize,
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def close_out(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
        :code:`OnComplete` set to :code:`CloseOut` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of :code:`Txn.sender()` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and
            attributes set in it's :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(close_out=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(close_out=CallConfig.CALL),
                authorize=authorize,
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)


def no_op(
    fn: HandlerFunc | None = None, /, *, authorize: SubroutineFnWrapper | None = None
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with
        it's :code:`OnComplete` set to :code:`NoOp` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of :code:`Txn.sender()` and output
            uint64 interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and
            attributes set in it's :code:`__handler_config__`
    """

    def _impl(fn: HandlerFunc) -> HandlerFunc:
        if is_bare(fn):
            if authorize is not None:
                fn = _authorize(authorize)(fn)
            return bare_external(no_op=CallConfig.CALL)(fn)
        else:
            return external(
                method_config=MethodConfig(no_op=CallConfig.CALL), authorize=authorize
            )(
                fn
            )  # type: ignore

    if fn is None:
        return _impl

    return _impl(fn)
