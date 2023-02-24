from pyteal import Approve, Expr

from beaker import Application

__all__ = [
    "unconditional_create_approval",
    "unconditional_opt_in_approval",
]


def unconditional_create_approval(
    app: Application, *, initialize_global_state: bool = False
) -> None:
    @app.create
    def create() -> Expr:
        if initialize_global_state:
            return app.initialize_global_state()
        return Approve()


def unconditional_opt_in_approval(
    app: Application, *, initialize_local_state: bool = False
) -> None:
    @app.opt_in
    def opt_in() -> Expr:
        if initialize_local_state:
            return app.initialize_local_state()
        return Approve()
