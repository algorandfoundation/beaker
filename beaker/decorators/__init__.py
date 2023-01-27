import inspect
from dataclasses import dataclass, field
from enum import Enum
from inspect import signature, Parameter
from typing import Callable, Any, TypedDict

from pyteal import abi, Expr, Int, TealTypeError, Bytes, ABIReturnSubroutine

from beaker.decorators.authorize import _authorize, Authorize
from beaker.state import AccountStateValue, ApplicationStateValue

HandlerFunc = Callable[..., Expr]


class DefaultArgumentClass(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


DefaultArgumentType = Expr | ABIReturnSubroutine | int | bytes | str


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


class StructArgDict(TypedDict):
    name: str
    elements: list[tuple[str, str]]


@dataclass
class MethodHints:
    """MethodHints provides hints to the caller about how to call the method"""

    #: hint to indicate this method can be called through Dryrun
    read_only: bool = field(default=False)
    #: hint to provide names for tuple argument indices
    #: method_name=>param_name=>{name:str, elements:[str,str]}
    structs: dict[str, StructArgDict] = field(default_factory=dict)
    #: defaults
    default_arguments: dict[str, DefaultArgument] = field(default_factory=dict)

    def empty(self) -> bool:
        return not self.dictify()

    def dictify(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.read_only:
            d["read_only"] = True
        if self.default_arguments:
            d["default_arguments"] = {
                k: v.dictify() for k, v in self.default_arguments.items()
            }
        if self.structs:
            d["structs"] = self.structs
        return d


def capture_method_hints_and_remove_defaults(
    fn: HandlerFunc, read_only: bool
) -> MethodHints:
    sig = signature(fn)
    params = sig.parameters.copy()

    mh = MethodHints(read_only=read_only)

    for name, param in params.items():
        match param.default:
            case Expr() | int() | str() | bytes() | ABIReturnSubroutine():
                mh.default_arguments[name] = DefaultArgument(param.default)
                params[name] = param.replace(default=Parameter.empty)
        if inspect.isclass(param.annotation) and issubclass(
            param.annotation, abi.NamedTuple
        ):
            mh.structs[name] = {
                "name": str(param.annotation.__name__),
                "elements": [
                    (name, str(abi.algosdk_from_annotation(typ.__args__[0])))
                    for name, typ in param.annotation.__annotations__.items()
                ],
            }

    if mh.default_arguments:
        # Fix function sig/annotations
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]

    return mh
