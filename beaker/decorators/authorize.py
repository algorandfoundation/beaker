from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from pyteal import (
    Expr,
    SubroutineFnWrapper,
    TealType,
    TealTypeError,
    Subroutine,
    Seq,
    AssetHolding,
    And,
    Int,
    Global,
    App,
    TealInputError,
    Assert,
    Txn,
)


# TODO: refactor this to be more of an Expr builder so it becomes composable
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


HandlerReturn = TypeVar("HandlerReturn", bound=Expr)
HandlerParams = ParamSpec("HandlerParams")


def _authorize(
    allowed: SubroutineFnWrapper,
) -> Callable[[Callable[HandlerParams, HandlerReturn]], Callable[HandlerParams, Expr]]:
    auth_sub_args = allowed.subroutine.expected_arg_types

    if len(auth_sub_args) != 1 or auth_sub_args[0] is not Expr:
        raise TealInputError(
            "Expected a single expression argument to authorize function"
        )

    if allowed.type_of() != TealType.uint64:
        raise TealTypeError(allowed.type_of(), TealType.uint64)

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
