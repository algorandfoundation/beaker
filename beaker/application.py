from typing import Final, cast

from pyteal import (
    MAX_TEAL_VERSION,
    ABIReturnSubroutine,
    Approve,
    BareCallActions,
    CallConfig,
    Expr,
    Global,
    OnCompleteAction,
    OptimizeOptions,
    Reject,
    Router,
    TealInputError,
    Bytes,
)

from .decorators import bare_handler, get_handler_config, _bare_method, _abi_method
from .application_schema import (
    AccountState,
    ApplicationState,
    DynamicLocalStateValue,
    LocalStateValue,
    GlobalStateValue,
    DynamicGlobalStateValue,
)

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

        attrs = {a: getattr(self, a) for a in custom_attrs}

        self.acct_vals = {}
        self.app_vals = {}
        for k, v in attrs.items():
            match v:
                case LocalStateValue():
                    if v.key is None:
                        v.key = Bytes(k)
                    self.acct_vals[k] = v
                case GlobalStateValue():
                    if v.key is None:
                        v.key = Bytes(k)
                    self.app_vals[k] = v
                case DynamicLocalStateValue():
                    self.acct_vals[k] = v
                case DynamicGlobalStateValue():
                    self.app_vals[k] = v

        self.acct_state = AccountState(self.acct_vals)
        self.app_state = ApplicationState(self.app_vals)

        self.bare_handlers = {}
        self.methods = {}
        for name, bound_attr in attrs.items():
            handler_config = get_handler_config(bound_attr)

            if _abi_method in handler_config:
                abi_meth = cast(ABIReturnSubroutine, handler_config[_abi_method])
                abi_meth.subroutine.implementation = bound_attr
                self.methods[name] = abi_meth

            if _bare_method in handler_config:
                ba = cast(BareCallActions, handler_config[_bare_method])
                for oc, action in ba.__dict__.items():
                    if action is None:
                        continue

                    action = cast(OnCompleteAction, action)

                    if oc in self.bare_handlers:
                        raise TealInputError(f"Tried to overwrite a bare handler: {oc}")

                    # Swap the implementation with the bound version
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

    @bare_handler(no_op=CallConfig.CREATE)
    def create(self):
        return Approve()

    @bare_handler(update_application=CallConfig.ALL)
    def update(self):
        return Reject()

    @bare_handler(delete_application=CallConfig.ALL)
    def delete(self):
        return Reject()
