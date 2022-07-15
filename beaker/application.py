from inspect import getattr_static, signature
from typing import Final, cast, Callable
from algosdk.abi import Method
from pyteal import (
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
    Bare,
    HandlerConfig,
    MethodHints,
    get_handler_config,
)
from .application_schema import (
    AccountState,
    ApplicationState,
    DynamicLocalStateValue,
    LocalStateValue,
    GlobalStateValue,
    DynamicGlobalStateValue,
)
from .errors import BareOverwriteError


def method_spec(fn) -> Method:
    hc = get_handler_config(fn)
    if hc.method_spec is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.method_spec


class Application:
    """Application should be subclassed to add functionality"""

    # Convenience constant fields
    address: Final[Expr] = Global.current_application_address()
    id: Final[Expr] = Global.current_application_id()

    def __init__(self, version: int = MAX_TEAL_VERSION):
        self.teal_version = version

        self.attrs = {
            m: getattr(self, m)
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.hints: dict[str, MethodHints] = {}
        self.bare_handlers: dict[str, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, MethodConfig]] = {}

        acct_vals: dict[str, LocalStateValue | DynamicLocalStateValue] = {}
        app_vals: dict[str, GlobalStateValue | DynamicGlobalStateValue] = {}

        for name, bound_attr in self.attrs.items():
            static_attr = getattr_static(self, name)
            handler_config = get_handler_config(bound_attr)
            self.hints[name] = handler_config.hints()

            match (bound_attr, handler_config):
                case (DynamicLocalStateValue(), _):
                    acct_vals[name] = bound_attr
                case (LocalStateValue(), _):
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    acct_vals[name] = bound_attr
                case (DynamicGlobalStateValue(), _):
                    app_vals[name] = bound_attr
                case (GlobalStateValue(), _):
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    app_vals[name] = bound_attr
                case (_, HandlerConfig(method_spec=Method())):
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if handler_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr
                    self.methods[name] = (abi_meth, handler_config.method_config)
                case (_, HandlerConfig(subroutine=Subroutine())):
                    if handler_config.referenced_self:
                        # Add the `self` bound method, wrapped in a subroutine
                        setattr(self, name, handler_config.subroutine(bound_attr))
                    else:
                        # Add the static method, wrapped in a subroutine on the class since we didn't reference `self`
                        setattr(
                            self.__class__,
                            name,
                            handler_config.subroutine(static_attr),
                        )
                case (_, HandlerConfig(bare_method=BareCallActions())):
                    ba = handler_config.bare_method
                    for oc, action in ba.__dict__.items():
                        if action is None:
                            continue

                        if oc in self.bare_handlers:
                            raise BareOverwriteError(oc)

                        action = cast(OnCompleteAction, action)
                        # Swap the implementation with the bound version
                        if handler_config.referenced_self:
                            action.action.subroutine.implementation = bound_attr

                        self.bare_handlers[oc] = action

        self.acct_state = AccountState(acct_vals)
        self.app_state = ApplicationState(app_vals)

        # Create router with name of class and bare handlers
        self.router = Router(type(self).__name__, BareCallActions(**self.bare_handlers))

        # Add method handlers
        for method, method_config in self.methods.values():
            self.router.add_method_handler(
                method_call=method, method_config=method_config
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

    def initialize_account_state(self, addr):
        return self.acct_state.initialize(addr)

    @Bare.create
    def create(self):
        return Approve()

    @Bare.update
    def update(self):
        return Reject()

    @Bare.delete
    def delete(self):
        return Reject()

    @Bare.opt_in
    def opt_in(self):
        return Reject()

    @Bare.close_out
    def close_out(self):
        return Reject()

    @Bare.clear_state
    def clear_state(self):
        return Reject()
