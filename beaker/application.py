from inspect import getattr_static
from typing import Final, cast
from algosdk.abi import Method
from pyteal import (
    MAX_TEAL_VERSION,
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
)

from .decorators import (
    Bare,
    MethodHints,
    get_handler_config,
    set_handler_config,
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
    if hc.abi_method is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.abi_method.method_spec()


class Application:
    """Application should be subclassed to add functionality"""

    # Convenience constant fields
    address: Final[Expr] = Global.current_application_address()
    id: Final[Expr] = Global.current_application_id()

    bare_methods: BareCallActions

    def __init__(self, version: int = MAX_TEAL_VERSION):
        self.teal_version = version

        self.attrs = {
            m: getattr(self, m)
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        acct_vals: dict[str, LocalStateValue | DynamicLocalStateValue] = {}
        app_vals: dict[str, GlobalStateValue | DynamicGlobalStateValue] = {}

        for k, v in self.attrs.items():
            if isinstance(v, LocalStateValue) or isinstance(v, GlobalStateValue):
                if v.key is None:
                    v.key = Bytes(k)

            match v:
                case LocalStateValue() | DynamicLocalStateValue():
                    acct_vals[k] = v
                case GlobalStateValue() | DynamicGlobalStateValue():
                    app_vals[k] = v

        self.acct_state = AccountState(acct_vals)
        self.app_state = ApplicationState(app_vals)

        self.hints: dict[str, MethodHints] = {}
        self.bare_handlers: dict[str, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, MethodConfig]] = {}
        for name, bound_attr in self.attrs.items():
            handler_config = get_handler_config(bound_attr)

            h = handler_config.hints()
            if len(h.__dict__.keys()) > 0:
                self.hints[name] = h

            # Add ABI handlers
            if handler_config.abi_method is not None:
                abi_meth = handler_config.abi_method

                # Swap the implementation with the bound version
                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

                self.methods[name] = (abi_meth, handler_config.method_config)

            # Add internal subroutines
            if handler_config.subroutine is not None:
                if handler_config.referenced_self:
                    # Add the `self` bound method, wrapped in a subroutine
                    setattr(self, name, handler_config.subroutine(bound_attr))
                else:
                    # Add the static method, wrapped in a subroutine on the class since we didn't reference `self`
                    setattr(
                        self.__class__,
                        name,
                        handler_config.subroutine(getattr_static(self, name)),
                    )

            # Add bare handlers
            if handler_config.bare_method is not None:
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
