from inspect import getattr_static
from typing import Final, cast
from algosdk.abi import Method
from pyteal import (
    Txn,
    MAX_TEAL_VERSION,
    Expr,
    ABIReturnSubroutine,
    Approve,
    BareCallActions,
    Expr,
    Global,
    MethodConfig,
    OnCompleteAction,
    OptimizeOptions,
    Reject,
    Router,
    Bytes,
    Subroutine,
)

from .decorators import (
    HandlerConfig,
    MethodHints,
    get_handler_config,
    create,
    update,
    delete,
    opt_in,
    close_out,
    clear_state,
)
from .application_schema import (
    AccountState,
    ApplicationState,
    DynamicAccountStateValue,
    AccountStateValue,
    ApplicationStateValue,
    DynamicApplicationStateValue,
)
from .errors import BareOverwriteError


def get_method_spec(fn) -> Method:
    hc = get_handler_config(fn)
    if hc.method_spec is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.method_spec


def get_method_signature(fn) -> str:
    return get_method_spec(fn).get_signature()


def get_method_selector(fn) -> str:
    return get_method_spec(fn).get_selector()


class Application:
    """Application should be subclassed to add functionality"""

    # Convenience constant fields
    address: Final[Expr] = Global.current_application_address()
    id: Final[Expr] = Global.current_application_id()

    def __init__(self, version: int = MAX_TEAL_VERSION):
        self.teal_version = version

        self.attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.hints: dict[str, MethodHints] = {}
        self.bare_handlers: dict[str, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, MethodConfig]] = {}

        acct_vals: dict[str, AccountStateValue | DynamicAccountStateValue] = {}
        app_vals: dict[str, ApplicationStateValue | DynamicApplicationStateValue] = {}

        for name, (bound_attr, static_attr) in self.attrs.items():

            # Check for state vals
            match bound_attr:
                case AccountStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    acct_vals[name] = bound_attr
                case DynamicAccountStateValue():
                    acct_vals[name] = bound_attr
                case ApplicationStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    app_vals[name] = bound_attr
                case DynamicApplicationStateValue():
                    app_vals[name] = bound_attr

            if name in app_vals or name in acct_vals:
                continue

            # Check for handlers and internal methods
            handler_config = get_handler_config(bound_attr)
            match handler_config:
                # Bare Handlers
                case HandlerConfig(bare_method=BareCallActions()):
                    actions = {
                        oc: cast(OnCompleteAction, action)
                        for oc, action in handler_config.bare_method.__dict__.items()
                        if action is not None
                    }

                    for oc, action in actions.items():
                        if oc in self.bare_handlers:
                            raise BareOverwriteError(oc)

                        # Swap the implementation with the bound version
                        if handler_config.referenced_self:
                            action.action.subroutine.implementation = bound_attr

                        self.bare_handlers[oc] = action

                # ABI Methods
                case HandlerConfig(method_spec=Method()):
                    # Create the ABIReturnSubroutine from the static attr
                    # but override the implementation with the bound version
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if handler_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr
                    self.methods[name] = abi_meth

                    self.hints[name] = handler_config.hints()

                # Internal subroutines
                case HandlerConfig(subroutine=Subroutine()):
                    if handler_config.referenced_self:
                        setattr(self, name, handler_config.subroutine(bound_attr))
                    else:
                        setattr(
                            self.__class__,
                            name,
                            handler_config.subroutine(static_attr),
                        )

        self.acct_state = AccountState(acct_vals)
        self.app_state = ApplicationState(app_vals)

        # Create router with name of class and bare handlers
        self.router = Router(
            name=self.__class__.__name__,
            bare_calls=BareCallActions(**self.bare_handlers),
        )

        # Add method handlers
        for method in self.methods.values():
            self.router.add_method_handler(
                method_call=method, method_config=handler_config.method_config
            )

        (
            self.approval_program,
            self.clear_program,
            self.contract,
        ) = self.router.compile_program(
            version=self.teal_version,
            assemble_constants=True,
            optimize=OptimizeOptions(scratch_slots=True),
        )

    def initialize_app_state(self):
        return self.app_state.initialize()

    def initialize_account_state(self, addr=Txn.sender()):
        return self.acct_state.initialize(addr)

    @create
    def create(self):
        return Approve()

    @update
    def update(self):
        return Reject()

    @delete
    def delete(self):
        return Reject()

    @opt_in
    def opt_in(self):
        return self.initialize_account_state()

    @close_out
    def close_out(self):
        return Reject()

    @clear_state
    def clear_state(self):
        return Reject()
