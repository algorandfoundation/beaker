from inspect import getattr_static
from typing import Final, Any, cast
from algosdk.abi import Method
from pyteal import (
    Txn,
    MAX_TEAL_VERSION,
    ABIReturnSubroutine,
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

from beaker.decorators import (
    externalConfig,
    MethodHints,
    get_external_config,
    create,
    update,
    delete,
    opt_in,
    close_out,
    clear_state,
)
from beaker.state import (
    AccountState,
    ApplicationState,
    DynamicAccountStateValue,
    AccountStateValue,
    ApplicationStateValue,
    DynamicApplicationStateValue,
)
from beaker.errors import BareOverwriteError


def get_method_spec(fn) -> Method:
    hc = get_external_config(fn)
    if hc.method_spec is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.method_spec


def get_method_signature(fn) -> str:
    return get_method_spec(fn).get_signature()


def get_method_selector(fn) -> bytes:
    return get_method_spec(fn).get_selector()


class Application:
    """Application contains logic to detect State Variables, Bare methods
    ABI Methods and internal subroutines.

    It should be subclassed to provide basic behavior to a custom application.
    """

    # Convenience constant fields
    address: Final[Expr] = Global.current_application_address()
    id: Final[Expr] = Global.current_application_id()

    def __init__(self, version: int = MAX_TEAL_VERSION):
        """Initialize the Application, finding all the custom attributes and initializing the Router"""
        self.teal_version = version

        # Is there a better way to get all the attrs declared in subclasses?
        self.attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.hints: dict[str, MethodHints] = {}
        self.bare_externals: dict[str, OnCompleteAction] = {}
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

            # Check for externals and internal methods
            external_config = get_external_config(bound_attr)
            match external_config:
                # Bare externals
                case externalConfig(bare_method=BareCallActions()):
                    actions = {
                        oc: cast(OnCompleteAction, action)
                        for oc, action in external_config.bare_method.__dict__.items()
                        if action is not None
                    }

                    for oc, action in actions.items():
                        if oc in self.bare_externals:
                            raise BareOverwriteError(oc)

                        # Swap the implementation with the bound version
                        if external_config.referenced_self:
                            action.action.subroutine.implementation = bound_attr

                        self.bare_externals[oc] = action

                # ABI Methods
                case externalConfig(method_spec=Method()):
                    # Create the ABIReturnSubroutine from the static attr
                    # but override the implementation with the bound version
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if external_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr
                    self.methods[name] = abi_meth

                    self.hints[name] = external_config.hints()

                # Internal subroutines
                case externalConfig(subroutine=Subroutine()):
                    if external_config.referenced_self:
                        setattr(self, name, external_config.subroutine(bound_attr))
                    else:
                        setattr(
                            self.__class__,
                            name,
                            external_config.subroutine(static_attr),
                        )

        self.acct_state = AccountState(acct_vals)
        self.app_state = ApplicationState(app_vals)

        # Create router with name of class and bare externals
        self.router = Router(
            name=self.__class__.__name__,
            bare_calls=BareCallActions(**self.bare_externals),
            descr=self.__doc__,
        )

        # Add method externals
        for method in self.methods.values():
            self.router.add_method_handler(
                method_call=method, method_config=external_config.method_config
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

    def application_spec(self) -> dict[str, Any]:
        """returns a dictionary, helpful to provide to callers with information about the application specification"""
        return {
            "hints": {k: v.dictify() for k, v in self.hints.items()},
            "schema": {
                "local": self.acct_state.dictify(),
                "global": self.app_state.dictify(),
            },
            "contract": self.contract.dictify(),
        }

    def initialize_application_state(self) -> Expr:
        """Initialize any application state variables declared"""
        return self.app_state.initialize()

    def initialize_account_state(self, addr=Txn.sender()) -> Expr:
        """
        Initialize any account state variables declared

        :param addr: Optional, address of account to initialize state for.
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """

        return self.acct_state.initialize(addr)

    @create
    def create(self) -> Expr:
        """default create behavior, initializes application state"""
        return self.initialize_application_state()

    @opt_in
    def opt_in(self) -> Expr:
        """default opt in behavior, initializes account state"""
        return self.initialize_account_state()

    @update
    def update(self) -> Expr:
        """default update behavior, rejects"""
        return Reject()

    @delete
    def delete(self) -> Expr:
        """default delete behavior, rejects"""
        return Reject()

    @close_out
    def close_out(self) -> Expr:
        """default close out behavior, rejects"""
        return Reject()

    @clear_state
    def clear_state(self) -> Expr:
        """default clear state behavior, rejects"""
        return Reject()
