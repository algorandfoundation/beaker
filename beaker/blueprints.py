from pyteal import Expr, Approve

from beaker import Application

__all__ = [
    "unconditional_create_approval",
    "unconditional_opt_in_approval",
]


def unconditional_create_approval(
    app: Application, initialize_app_state: bool = False
) -> None:
    @app.create
    def create() -> Expr:
        if initialize_app_state:
            return app.initialize_application_state()
        return Approve()


def unconditional_opt_in_approval(
    app: Application, initialize_account_state: bool = False
) -> None:
    @app.opt_in
    def opt_in() -> Expr:
        if initialize_account_state:
            return app.initialize_account_state()
        return Approve()
