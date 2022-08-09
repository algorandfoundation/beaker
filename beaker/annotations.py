from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, TypeVar, Annotated, Any, cast, Optional

from pyteal import (
    abi,
    Expr,
    Bytes,
    Int,
    TxnField,
)
from beaker.decorators import HandlerFunc, get_handler_config
from beaker.state import AccountStateValue, ApplicationStateValue

CheckExpr = Callable[..., Expr]
ABIType = TypeVar("ABIType", bound=abi.BaseType)


ResolvableType = AccountStateValue | ApplicationStateValue | HandlerFunc | Bytes | Int


class ResolvableClass(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


class ResolvableArgument:
    """ResolvableArgument is a container for any arguments that may be resolved prior to calling some target method"""

    def __init__(
        self,
        resolver: ResolvableType,
    ):
        self.resolve_type: ResolvableClass = None
        self.resolver = resolver

        self.resolve_with: str | int | dict[str, Any] = None
        match resolver:
            case AccountStateValue():
                self.resolve_from = ResolvableClass.LocalState
                self.resolve_with = resolver.str_key()
            case ApplicationStateValue():
                self.resolve_from = ResolvableClass.GlobalState
                self.resolve_with = resolver.str_key()
            case Bytes():
                self.resolve_from = ResolvableClass.Constant
                self.resolve_with = resolver.byte_str.replace('"', "")
            case Int():
                self.resolve_from = ResolvableClass.Constant
                self.resolve_with = resolver.value
            case _:
                # Fall through, if its not got a valid handler config, raise error
                hc = get_handler_config(cast(HandlerFunc, resolver))
                if hc.method_spec is None or not hc.read_only:
                    raise Exception(
                        "Expected str, int, ApplicationStateValue, AccountStateValue or read only ABI method"
                    )
                self.resolve_from = ResolvableClass.ABIMethod
                self.resolve_with = hc.method_spec.dictify()

    def resolve(self) -> Expr:
        if self.resolve_from == ResolvableClass.ABIMethod:
            return self.resolver()

        return self.resolver


class TransactionMatcher:
    def __init__(self, fields: dict[TxnField, Expr | CheckExpr]):
        self.fields = fields

    def get_checks(self, t: abi.Transaction) -> list[Expr]:
        checks = []

        for field, field_val in self.fields.items():
            field_getter = t.get().makeTxnExpr(field)
            match field_val:
                case Expr():
                    checks.append(field_getter == field_val)
                case CheckExpr():
                    checks.append(field_val(field_getter))

        return checks


@dataclass
class ParameterAnnotation:
    checks: Optional[list[Expr]] = field(kw_only=True, default=None)
    descr: Optional[str] = field(kw_only=True, default=None)
    default: Optional[ResolvableArgument] = field(kw_only=True, default=None)


def annotated(
    t: ABIType,
    descr: str = None,
    default: ResolvableType = None,
    check: Expr | dict[TxnField, Expr | Callable[..., Expr]] = None,
) -> ABIType:

    pa: ParameterAnnotation = ParameterAnnotation(descr=descr)

    match t:
        case abi.Transaction():
            if default is not None:
                raise Exception("Default may not be set on a transaction")

            pa = ParameterAnnotation(
                checks=TransactionMatcher(check).get_checks(), descr=descr
            )

        case abi.ReferenceType():
            pa = ParameterAnnotation(
                default=ResolvableArgument(default), descr=descr, check=check
            )

        case abi.BaseType():
            pass

    return Annotated[t, pa]
