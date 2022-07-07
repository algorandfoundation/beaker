from inspect import getattr_static
from typing import Final

from pyteal import (
    MAX_TEAL_VERSION,
    ABIReturnSubroutine,
    Approve,
    BareCallActions,
    CallConfig,
    Expr,
    Global,
    OptimizeOptions,
    Reject,
    Router,
    TealInputError,
)

from .decorators import bare_handler, get_handler_config
from .application_schema import AccountState, ApplicationState


class EmptyAppState(ApplicationState):
    """Default app state for Application class, no class variables defined"""


class EmptyAccountState(AccountState):
    """Default account state for Application class, no class variables defined"""


class Application:
    """Application should be subclassed to add functionality"""

    app_state: ApplicationState = EmptyAppState()
    acct_state: AccountState = EmptyAccountState()

    # Convenience constant fields
    address: Final[Expr] = Global.current_application_address()
    id: Final[Expr] = Global.current_application_id()

    bare_methods: BareCallActions

    def __init__(self):
        attrs = [
            getattr_static(self, m)
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        ]

        self.bare_calls = [c.__dict__ for c in attrs if isinstance(c, BareCallActions)]
        bare_handlers = {}
        for bm in self.bare_calls:
            for k, v in bm.items():
                if v is None:
                    continue

                if k in bare_handlers:
                    raise TealInputError(f"Tried to overwrite a bare handler: {k}")

                bare_handlers[k] = v

        self.router = Router(type(self).__name__, BareCallActions(**bare_handlers))

        self.methods = [c for c in attrs if isinstance(c, ABIReturnSubroutine)]
        for method in self.methods:
            self.router.add_method_handler(method, **get_handler_config(method))

        (
            self.approval_program,
            self.clear_program,
            self.contract,
        ) = self.router.compile_program(
            version=MAX_TEAL_VERSION,
            assemble_constants=True,
            optimize=OptimizeOptions(scratch_slots=True),
        )

    @bare_handler(no_op=CallConfig.CREATE)
    def create():
        return Approve()

    @bare_handler(update_application=CallConfig.ALL)
    def update():
        return Reject()

    @bare_handler(delete_application=CallConfig.ALL)
    def delete():
        return Reject()
