from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from pyteal import (
    And,
    App,
    Assert,
    AssetHolding,
    Expr,
    Global,
    Int,
    Seq,
    SubroutineFnWrapper,
    TealInputError,
    TealType,
    Txn,
)
from pyteal.types import require_type

__all__ = [
    "Authorize",
    "authorize",
]


# TODO: refactor this to be more of an Expr builder so it becomes composable
class Authorize:
    """
    Authorize contains methods that may be used as values to
    the `authorize` keyword of the `handle` decorator
    """

    @staticmethod
    def only(addr: Expr) -> Expr:
        """require that the sender of the app call match exactly the address passed"""
        require_type(addr, TealType.bytes)
        return Txn.sender() == addr

    @staticmethod
    def holds_token(asset_id: Expr) -> Expr:
        """require that the sender of the app call holds >0 of the asset id passed"""
        require_type(asset_id, TealType.uint64)
        return Seq(
            bal := AssetHolding.balance(Txn.sender(), asset_id),
            And(bal.hasValue(), bal.value() > Int(0)),
        )

    @staticmethod
    def opted_in(
        app_id: Expr = Global.current_application_id(),  # noqa: B008
    ) -> Expr:
        """require that the sender of the app call has
        already opted-in to a given app id"""
        require_type(app_id, TealType.uint64)
        return App.optedIn(Txn.sender(), app_id)


HandlerReturn = TypeVar("HandlerReturn", bound=Expr)
HandlerParams = ParamSpec("HandlerParams")


def authorize(
    allowed: Expr | SubroutineFnWrapper,
) -> Callable[[Callable[HandlerParams, HandlerReturn]], Callable[HandlerParams, Expr]]:

    if isinstance(allowed, SubroutineFnWrapper):
        auth_sub_args = allowed.subroutine.expected_arg_types

        if len(auth_sub_args) != 1 or auth_sub_args[0] is not Expr:
            raise TealInputError(
                "Expected a single expression argument to authorize function"
            )
        require_type(allowed, TealType.uint64)
        expr = allowed(Txn.sender())
    else:
        require_type(allowed, TealType.uint64)
        expr = allowed

    def decorator(
        fn: Callable[HandlerParams, HandlerReturn]
    ) -> Callable[HandlerParams, Expr]:
        @wraps(fn)
        def wrapped(*args: HandlerParams.args, **kwargs: HandlerParams.kwargs) -> Expr:
            return Seq(
                Assert(expr, comment="unauthorized"),
                fn(*args, **kwargs),
            )

        return wrapped

    return decorator
