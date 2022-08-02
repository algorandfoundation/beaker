from inspect import getattr_static
from typing import Final, Any, cast, Optional
from algosdk.abi import Method
from pyteal import (
    SubroutineFnWrapper,
    TealInputError,
    Txn,
    MAX_TEAL_VERSION,
    MethodConfig,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
    Global,
    OnCompleteAction,
    OptimizeOptions,
    Router,
    Bytes,
)

from beaker.decorators import (
    get_handler_config,
    MethodHints,
    create,
    opt_in,
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
    hc = get_handler_config(fn)
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
        self.methods: dict[str, ABIReturnSubroutine] = {}

        acct_vals: dict[str, AccountStateValue | DynamicAccountStateValue] = {}
        app_vals: dict[str, ApplicationStateValue | DynamicApplicationStateValue] = {}

        methods: dict[str, tuple[ABIReturnSubroutine, Optional[MethodConfig]]] = {}
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
            handler_config = get_handler_config(bound_attr)

            # Bare externals
            if handler_config.bare_method is not None:
                actions = {
                    oc: cast(OnCompleteAction, action)
                    for oc, action in handler_config.bare_method.__dict__.items()
                    if action.action is not None
                }

                for oc, action in actions.items():
                    if oc in self.bare_externals:
                        raise BareOverwriteError(oc)

                    # Swap the implementation with the bound version
                    if handler_config.referenced_self:
                        if not (
                            isinstance(action.action, SubroutineFnWrapper)
                            or isinstance(action.action, ABIReturnSubroutine)
                        ):
                            raise TealInputError(
                                f"Expected Subroutine or ABIReturnSubroutine, for {oc} got {action.action}"
                            )
                        action.action.subroutine.implementation = bound_attr

                    self.bare_externals[oc] = action

            # ABI externals
            elif handler_config.method_spec is not None:
                # Create the ABIReturnSubroutine from the static attr
                # but override the implementation with the bound version
                abi_meth = ABIReturnSubroutine(static_attr)
                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr
                methods[name] = (abi_meth, handler_config.method_config)

                self.hints[name] = handler_config.hints()

            # Internal subroutines
            elif handler_config.subroutine is not None:
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

        # Create router with name of class and bare externals
        self.router = Router(
            name=self.__class__.__name__,
            bare_calls=BareCallActions(**self.bare_externals),
            descr=self.__doc__,
        )

        # Add method externals
        for method_name, method_tuple in methods.items():
            method, method_config = method_tuple
            self.methods[method_name] = method
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
