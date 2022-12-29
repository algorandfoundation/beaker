from functools import wraps
from typing import Callable

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

HandlerFunc = Callable[..., Expr]


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
