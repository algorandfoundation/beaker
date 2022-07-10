from inspect import getattr_static
from typing import Final, cast
from algosdk.abi import Method
from pyteal import (
    MAX_TEAL_VERSION,
    Approve,
    BareCallActions,
    Expr,
    Global,
    OnCompleteAction,
    OptimizeOptions,
    Reject,
    Router,
    TealInputError,
    Bytes,
)

from .decorators import (
    get_handler_config,
    bare_create,
    bare_delete,
    bare_opt_in,
    bare_update,
)
from .application_schema import (
    AccountState,
    ApplicationState,
    DynamicLocalStateValue,
    LocalStateValue,
    GlobalStateValue,
    DynamicGlobalStateValue,
)


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

    def __init__(self):
        custom_attrs = [
            m
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        ]

        self.attrs = {a: getattr(self, a) for a in custom_attrs}

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

        self.bare_handlers = {}
        self.methods = {}
        for name, bound_attr in self.attrs.items():
            handler_config = get_handler_config(bound_attr)

            if handler_config.abi_method is not None:
                abi_meth = handler_config.abi_method

                # Swap the implementation with the bound version
                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

                self.methods[name] = abi_meth

            if handler_config.subroutine is not None:
                if handler_config.referenced_self:
                    setattr(self, name, handler_config.subroutine(bound_attr))
                else:
                    setattr(
                        self,
                        name,
                        handler_config.subroutine(getattr_static(self, name)),
                    )

            if handler_config.bare_method is not None:
                ba = handler_config.bare_method
                for oc, action in ba.__dict__.items():
                    if action is None:
                        continue

                    if oc in self.bare_handlers:
                        raise TealInputError(
                            f"Tried to overwrite a bare handler: {oc}. If you're trying to override a default method in Application, be sure to use the same name as the method defined."
                        )

                    action = cast(OnCompleteAction, action)
                    # Swap the implementation with the bound version
                    if handler_config.referenced_self:
                        action.action.subroutine.implementation = bound_attr

                    self.bare_handlers[oc] = action

        self.router = Router(type(self).__name__, BareCallActions(**self.bare_handlers))

        for method in self.methods.values():
            self.router.add_method_handler(method)

        (
            self.approval_program,
            self.clear_program,
            self.contract,
        ) = self.router.compile_program(
            version=MAX_TEAL_VERSION,
            assemble_constants=True,
            optimize=OptimizeOptions(scratch_slots=True),
        )

    def initialize_app_state(self):
        return self.app_state.initialize()

    def initialize_account_state(self, sender):
        return self.acct_state.initialize(sender)

    @bare_create
    def create(self):
        return Approve()

    @bare_update
    def update(self):
        return Reject()

    @bare_delete
    def delete(self):
        return Reject()
