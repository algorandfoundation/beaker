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
    TealType,
    Txn,
)
from pyteal.types import require_type

__all__ = [
    "Authorize",
    "authorize",
    "AuthCallable",
]


AuthCallable = Callable[[Expr], Expr]
"""A function that takes Txn.sender() and returns a condition to assert"""


# TODO: refactor this to be more of an Expr builder so it becomes composable
class Authorize:
    """
    Authorize contains methods that may be used as values to
    the `authorize` keyword of the `handle` decorator
    """

    @classmethod
    def only_creator(cls) -> AuthCallable:
        """require that the sender of the app call match exactly the address of the app's creator"""
        return cls.only(Global.creator_address())

    @staticmethod
    def only(addr: Expr) -> AuthCallable:
        """require that the sender of the app call match exactly the address passed"""
        require_type(addr, TealType.bytes)
        return lambda sender: sender == addr

    @staticmethod
    def holds_token(asset_id: Expr) -> AuthCallable:
        """require that the sender of the app call holds >0 of the asset id passed"""
        require_type(asset_id, TealType.uint64)
        return lambda sender: Seq(
            bal := AssetHolding.balance(sender, asset_id),
            And(bal.hasValue(), bal.value() > Int(0)),
        )

    @staticmethod
    def opted_in(
        app_id: Expr = Global.current_application_id(),  # noqa: B008
    ) -> AuthCallable:
        """require that the sender of the app call has
        already opted-in to a given app id"""
        require_type(app_id, TealType.uint64)
        return lambda sender: App.optedIn(sender, app_id)


HandlerReturn = TypeVar("HandlerReturn", bound=Expr)
HandlerParams = ParamSpec("HandlerParams")


def authorize(
    allowed: AuthCallable | SubroutineFnWrapper,
) -> Callable[[Callable[HandlerParams, HandlerReturn]], Callable[HandlerParams, Expr]]:
    def decorator(
        fn: Callable[HandlerParams, HandlerReturn]
    ) -> Callable[HandlerParams, Expr]:
        @wraps(fn)
        def wrapped(*args: HandlerParams.args, **kwargs: HandlerParams.kwargs) -> Expr:
            return Seq(
                Assert(allowed(Txn.sender()), comment="unauthorized"),
                fn(*args, **kwargs),
            )

        return wrapped

    return decorator
