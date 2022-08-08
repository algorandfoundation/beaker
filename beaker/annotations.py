from enum import Enum
from typing import Callable, TypeVar, Annotated, Any, cast

from pyteal import (
    abi,
    Expr
)

from beaker.decorators import HandlerFunc, get_handler_config
from beaker.state import AccountStateValue, ApplicationStateValue


AnnotationFunction = Callable[..., Expr]
ABIType = TypeVar('ABIType', bound=abi.BaseType)

def annotated(t: ABIType, *annos: AnnotationFunction) -> ABIType:
    assert len(annos)>0

    # Internally, python flattens nested Annotations so its safe
    # to loop and pass the annotated type to another Annotation
    for anno in annos:
        t = Annotated[t, anno]
    return t



def CheckedDefault(default_val: Any):
    pass

class ResolvableTypes(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


class ResolvableArgument:
    """ResolvableArgument is a container for any arguments that may be resolved prior to calling some target method"""

    def __init__(
        self,
        param_name: str,
        param_resolver: AccountStateValue | ApplicationStateValue | HandlerFunc | str | int
    ):

        self.parameter_name = param_name

        self.resolve_from: ResolvableTypes = None
        self.resolve_with: Any = None
        
        match param_resolver:
            case AccountStateValue():
                self.resolve_from = ResolvableTypes.LocalState
                self.resolve_with = param_resolver.str_key()
            case ApplicationStateValue():
                self.resolve_from = ResolvableTypes.GlobalState
                self.resolve_with = param_resolver.str_key()
            case str() | int():
                self.resolve_from = ResolvableTypes.Constant
                self.resolve_with = param_resolver
            case _:
                hc = get_handler_config(cast(HandlerFunc, param_resolver))
                if hc.method_spec is None or not hc.read_only:
                    raise Exception(
                        "Expected str, int, ApplicationStateValue, AccountStateValue or read only ABI method"
                    )
                self.resolve_from = ResolvableTypes.ABIMethod
                self.resolve_with = hc.method_spec.dictify()