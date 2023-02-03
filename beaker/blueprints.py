from pyteal import Expr, Approve

from beaker import Application, this_app


def unconditional_create_approval(
    app: Application, initialize_app_state: bool = False
) -> Application:
    @app.create
    def create() -> Expr:
        if initialize_app_state:
            return this_app().initialize_application_state()
        return Approve()

    return app


def unconditional_opt_in_approval(
    app: Application, initialize_account_state: bool = False
) -> Application:
    @app.opt_in
    def opt_in() -> Expr:
        if initialize_account_state:
            return this_app().initialize_account_state()
        return Approve()

    return app
