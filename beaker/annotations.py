from abc import ABC
from enum import Enum
from typing import Callable, TypeVar, Annotated, Any, cast

from pyteal import (
    TxnExpr,
    abi,
    Expr,
    Assert,
    Seq,
    Bytes,
    Int,
    TxnField,
)
from beaker.decorators import HandlerFunc, get_handler_config
from beaker.state import AccountStateValue, ApplicationStateValue

AnnotationFunction = Callable[..., Expr]
ABIType = TypeVar("ABIType", bound=abi.BaseType)


class ResolvableTypes(str, Enum):
    ABIMethod = "abi-method"
    LocalState = "local-state"
    GlobalState = "global-state"
    Constant = "constant"


class ResolvableArgument:
    """ResolvableArgument is a container for any arguments that may be resolved prior to calling some target method"""

    def __init__(
        self,
        resolver: AccountStateValue | ApplicationStateValue | HandlerFunc | Bytes | Int,
    ):
        self.resolve_type: ResolvableTypes = None
        self.resolver = resolver

        self.resolve_with: str | int | dict[str, Any] = None
        match resolver:
            case AccountStateValue():
                self.resolve_from = ResolvableTypes.LocalState
                self.resolve_with = resolver.str_key()
            case ApplicationStateValue():
                self.resolve_from = ResolvableTypes.GlobalState
                self.resolve_with = resolver.str_key()
            case Bytes():
                self.resolve_from = ResolvableTypes.Constant
                self.resolve_with = resolver.byte_str.replace('"', "")
            case Int():
                self.resolve_from = ResolvableTypes.Constant
                self.resolve_with = resolver.value
            case _:
                # Fall through, if its not got a valid handler config, raise error
                hc = get_handler_config(cast(HandlerFunc, resolver))
                if hc.method_spec is None or not hc.read_only:
                    raise Exception(
                        "Expected str, int, ApplicationStateValue, AccountStateValue or read only ABI method"
                    )
                self.resolve_from = ResolvableTypes.ABIMethod
                self.resolve_with = hc.method_spec.dictify()

    def resolve(self) -> Expr:
        if self.resolve_from == ResolvableTypes.ABIMethod:
            return self.resolver()

        return self.resolver


class TransactionMatcher:
    def __init__(self, fields: dict[TxnField, Expr]):
        self.fields = fields

    def get_checks(self, t: abi.Transaction) -> list[Expr]:
        return [
            t.get().makeTxnExpr(field) == field_val
            for field, field_val in self.fields.items()
        ]


def annotated(t: ABIType, *annotations: AnnotationFunction) -> ABIType:
    assert len(annotations) > 0

    # Internally, python flattens nested Annotations so its safe
    # to loop and pass the annotated type to another Annotation
    for anno in annotations:
        t = Annotated[t, anno]

    return t


def unchecked(val: Expr | ResolvableArgument) -> AnnotationFunction:
    match val:

        case Expr():

            def _impl(field):
                return Seq()

            return _impl

        case ResolvableArgument():

            def _impl(field):
                return Seq()

            return _impl

        case _:
            raise Exception(f"Invalid type of val: {val}")


def checked(val: Expr | ResolvableArgument | TransactionMatcher) -> AnnotationFunction:
    match val:

        case Expr():

            def _impl(arg):
                return Assert(arg == val)

            return _impl

        case ResolvableArgument():

            def _impl(arg):
                return Assert(arg == val.resolve())

            return _impl

        case TransactionMatcher():

            def _impl(arg):
                return Assert(*val.get_checks(arg))

            return _impl

        case _:
            raise Exception(f"Invalid type of val: {val}")
