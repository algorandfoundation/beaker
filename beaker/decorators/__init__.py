import functools
import inspect
from dataclasses import asdict, dataclass, field, astuple
from enum import Enum
from inspect import signature, Parameter
from typing import Optional, Callable, Final, cast, Any, TypeVar, overload, TypedDict
from types import FunctionType
from algosdk.abi import Method
from pyteal import (
    abi,
    ABIReturnSubroutine,
    BareCallActions,
    CallConfig,
    Expr,
    Int,
    MethodConfig,
    OnCompleteAction,
    Subroutine,
    SubroutineFnWrapper,
    TealInputError,
    TealType,
    TealTypeError,
    Bytes,
)

from beaker.decorators.authorize import _authorize, Authorize

from beaker.state import AccountStateValue, ApplicationStateValue

__all__ = [
    "Authorize",
    "external",
    "internal",
    # "bare_external",
    "create",
    "no_op",
    "update",
    "delete",
    "opt_in",
    "close_out",
    "clear_state",
    "ABIExternalMetadata",
]

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
class ABIExternalMetadata:
    method_config: MethodConfig = field(kw_only=True)
    name_override: str | None = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)
    authorize: SubroutineFnWrapper | None = field(kw_only=True, default=None)


@dataclass
class HandlerConfig:
    """HandlerConfig contains all the extra bits of info about a given ABI method"""

    method_spec: Optional[Method] = field(kw_only=True, default=None)
    subroutine: Optional[Subroutine] = field(kw_only=True, default=None)
    bare_method: Optional[BareCallActions] = field(kw_only=True, default=None)

    referenced_self: bool = field(kw_only=True, default=False)
    structs: Optional[dict[str, type[abi.NamedTuple]]] = field(
        kw_only=True, default=None
    )

    default_arguments: Optional[dict[str, DefaultArgument]] = field(
        kw_only=True, default=None
    )
    method_config: Optional[MethodConfig] = field(kw_only=True, default=None)
    read_only: bool = field(kw_only=True, default=False)

    def hints(self) -> "MethodHints":
        mh = MethodHints(read_only=self.read_only)

        if self.default_arguments:
            mh.default_arguments = self.default_arguments

        if self.structs:
            mh.structs = {
                arg_name: {
                    "name": str(model_spec.__name__),
                    "elements": [
                        (name, str(abi.algosdk_from_annotation(typ.__args__[0])))
                        for name, typ in model_spec.__annotations__.items()
                    ],
                }
                for arg_name, model_spec in self.structs.items()
            }
        return mh

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
    try:
        config = getattr(fn, _handler_config_attr)
    except AttributeError:
        return HandlerConfig()
    else:
        return cast(HandlerConfig, config)


class StructArgDict(TypedDict):
    name: str
    elements: list[tuple[str, str]]


@dataclass
class MethodHints:
    """MethodHints provides hints to the caller about how to call the method"""

    #: hint to indicate this method can be called through Dryrun
    read_only: bool = field(kw_only=True, default=False)
    #: hint to provide names for tuple argument indices
    #: method_name=>param_name=>{name:str, elements:[str,str]}
    structs: dict[str, StructArgDict] | None = field(kw_only=True, default=None)
    #: defaults
    default_arguments: dict[str, DefaultArgument] | None = field(
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


def _capture_structs(fn: HandlerFunc, config: HandlerConfig) -> None:
    params = signature(fn).parameters
    config.structs = {
        k: v.annotation
        for k, v in params.items()
        if inspect.isclass(v.annotation) and issubclass(v.annotation, abi.NamedTuple)
    }


def _capture_defaults(fn: HandlerFunc, config: HandlerConfig) -> None:
    sig = signature(fn)
    params = sig.parameters.copy()

    default_args: dict[str, DefaultArgument] = {}

    for k, v in params.items():
        match v.default:
            case Expr() | int() | str() | bytes() | FunctionType():
                default_args[k] = DefaultArgument(v.default)
                params[k] = v.replace(default=Parameter.empty)

    if default_args:
        # Update handler config
        config.default_arguments = default_args

        # Fix function sig/annotations
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]


def _remove_self(fn: HandlerFunc, config: HandlerConfig) -> None:
    sig = signature(fn)
    params = sig.parameters.copy()

    try:
        del params["self"]
    except KeyError:
        pass
    else:
        # Flag that this method did have a `self` argument
        config.referenced_self = True
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]


def internal(return_type: TealType) -> Callable[..., HandlerFunc]:
    """creates a subroutine to be called by logic internally

    Args:
        return_type: The type this method's returned Expression should evaluate to
    Returns:
        The wrapped subroutine
    """

    if not isinstance(return_type, TealType):
        raise TypeError("return_type must be a TealType")

    class Wrapper:
        def __init__(self, func: HandlerFunc):
            self._original_func = func

            sig = signature(self._original_func)
            new_sig = sig.replace(parameters=list(sig.parameters.values())[1:])
            func.__signature__ = new_sig  # type: ignore[attr-defined]

            self._subs: dict[Any, SubroutineFnWrapper] = {}

        def __get__(
            self, instance: Any, owner: type | None = None
        ) -> SubroutineFnWrapper:
            if instance is None:
                raise TypeError("Cannot invoke bound method from static context")

            try:
                return self._subs[instance]
            except KeyError:
                pass

            sub = Subroutine(return_type)(self._original_func)
            sub.subroutine.implementation = functools.partial(
                self._original_func, instance
            )
            self._subs[instance] = sub
            return sub

    def decorator(func: HandlerFunc) -> HandlerFunc:
        sig = signature(func)
        params = sig.parameters
        if params:
            first_param_name = next(iter(params))
            if first_param_name == "self":
                return Wrapper(func)  # type: ignore
        return Subroutine(return_type)(func)

    return decorator


@overload
def external(
    fn: HandlerFunc,
    /,
    *,
    name: str | None = None,
    authorize: SubroutineFnWrapper | None = None,
    method_config: MethodConfig | None = None,
    read_only: bool = False,
) -> HandlerFunc:
    ...


@overload
def external(
    *,
    name: str | None = None,
    authorize: SubroutineFnWrapper | None = None,
    method_config: MethodConfig | None = None,
    read_only: bool = False,
) -> Callable[..., HandlerFunc]:
    ...


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

    def _impl(f: HandlerFunc) -> HandlerFunc:
        config = get_handler_config(f)
        _remove_self(f, config)
        _capture_defaults(f, config)
        _capture_structs(f, config)

        if authorize is not None:
            f = _authorize(authorize)(f)

        config.method_config = method_config
        config.read_only = read_only
        config.method_spec = ABIReturnSubroutine(f, overriding_name=name).method_spec()
        setattr(f, _handler_config_attr, config)

        return f

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
        config = get_handler_config(fun)
        _remove_self(fun, config)

        sub = SubroutineFnWrapper(fun, return_type=TealType.none)

        def to_action(cc: CallConfig | None) -> OnCompleteAction:
            return (
                OnCompleteAction(action=sub, call_config=cc)
                if (cc is not None and cc is not CallConfig.NEVER)
                else OnCompleteAction.never()
            )

        config.bare_method = BareCallActions(
            no_op=to_action(no_op),
            delete_application=to_action(delete_application),
            update_application=to_action(update_application),
            opt_in=to_action(opt_in),
            close_out=to_action(close_out),
            clear_state=to_action(clear_state),
        )
        setattr(fun, _handler_config_attr, config)

        return fun

    return _impl


def is_bare(fn: HandlerFunc) -> bool:
    sig = signature(fn)
    return len(sig.parameters) == 0 or (
        len(sig.parameters) == 1 and "self" in sig.parameters
    )


def _on_completion(
    method_config: MethodConfig,
    *,
    fn: HandlerFunc | None = None,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    def _impl(f: HandlerFunc) -> HandlerFunc:
        # if not is_bare(f):
        if not bare:
            wrapper = external(method_config=method_config, authorize=authorize)
        else:
            if not is_bare(f):
                raise TypeError("bare methods must take no parameters")
            if authorize is not None:
                f = _authorize(authorize)(f)
            mconfig = asdict(method_config)
            wrapper = bare_external(**mconfig)
        return wrapper(f)

    if fn is None:
        return _impl
    return _impl(fn)


def create(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    method_config: MethodConfig | None = None,
    bare: bool = False,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with its :code:`OnComplete`
        set to :code:`NoOp` call and ApplicationId == 0

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and attributes set
        in it's `__handler_config__`
    """

    if method_config is None:
        method_config = MethodConfig(no_op=CallConfig.CREATE)
    elif not all(
        cc == CallConfig.CREATE or cc == CallConfig.ALL
        for cc in asdict(method_config).values()
    ):
        raise TealInputError(
            "method_config for create may not have non create call configs"
        )

    return _on_completion(method_config, fn=fn, authorize=authorize, bare=bare)


def delete(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
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
    return _on_completion(
        MethodConfig(delete_application=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )


def update(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
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
    return _on_completion(
        MethodConfig(update_application=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )


def opt_in(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
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
    return _on_completion(
        MethodConfig(opt_in=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )


def clear_state(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
        :code:`OnComplete` set to :code:`ClearState` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of ``Txn.sender()`` and output uint64
            interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and
            attributes set in it's :code:`__handler_config__`
    """
    return _on_completion(
        MethodConfig(clear_state=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )


def close_out(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
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
    return _on_completion(
        MethodConfig(close_out=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )


def no_op(
    fn: HandlerFunc | None = None,
    /,
    *,
    authorize: SubroutineFnWrapper | None = None,
    bare: bool = False,
) -> HandlerFunc | Callable[..., HandlerFunc]:
    """set method to be handled by an application call with it's
        :code:`OnComplete` set to :code:`NoOp` call

    Args:
        fn: The method to be wrapped.
        authorize: a subroutine with input of :code:`Txn.sender()` and output
            uint64 interpreted as allowed if the output>0.
    Returns:
        The original method with changes made to its signature and
            attributes set in it's :code:`__handler_config__`
    """
    return _on_completion(
        MethodConfig(no_op=CallConfig.CALL),
        fn=fn,
        authorize=authorize,
        bare=bare,
    )
