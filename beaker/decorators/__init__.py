import inspect
from dataclasses import dataclass, field
from enum import Enum
from inspect import signature, Parameter
from typing import Optional, Callable, Any, TypedDict

from algosdk.abi import Method
from pyteal import (
    abi,
    BareCallActions,
    Expr,
    Int,
    MethodConfig,
    Subroutine,
    TealTypeError,
    Bytes,
    ABIReturnSubroutine,
)

from beaker.decorators.authorize import _authorize, Authorize
from beaker.state import AccountStateValue, ApplicationStateValue

__all__ = [
    "Authorize",
]

HandlerFunc = Callable[..., Expr]

DefaultArgumentType = Expr | ABIReturnSubroutine | int | bytes | str


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
            case ABIReturnSubroutine() as fn:
                if not getattr(fn, "_read_only", None):
                    raise TealTypeError(self.resolver, DefaultArgumentType)
                self.resolvable_class = DefaultArgumentClass.ABIMethod
            case _:
                raise TealTypeError(self.resolver, DefaultArgumentType)

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
            case ABIReturnSubroutine() as fn:
                if not getattr(fn, "_read_only", None):
                    raise TealTypeError(self.resolver, DefaultArgumentType)
                return fn.method_spec().dictify()
            case _:
                raise TealTypeError(self.resolver, DefaultArgumentType)

    def dictify(self) -> dict[str, Any]:
        return {"source": self.resolvable_class.value, "data": self.resolve_hint()}


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


def _capture_structs_and_defaults(fn: HandlerFunc, config: HandlerConfig) -> None:
    sig = signature(fn)
    params = sig.parameters.copy()

    config.structs = {}
    config.default_arguments = {}

    for name, param in params.items():
        match param.default:
            case Expr() | int() | str() | bytes() | ABIReturnSubroutine():
                config.default_arguments[name] = DefaultArgument(param.default)
                params[name] = param.replace(default=Parameter.empty)
        if inspect.isclass(param.annotation) and issubclass(
            param.annotation, abi.NamedTuple
        ):
            config.structs[name] = param.annotation

    if config.default_arguments:
        # TODO: is this strictly required?
        # Fix function sig/annotations
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]
