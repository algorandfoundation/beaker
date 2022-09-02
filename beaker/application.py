import base64
from inspect import getattr_static
from typing import Final, Any, cast, Optional
from algosdk.abi import Method
from pyteal import (
    SubroutineFnWrapper,
    TealInputError,
    Txn,
    MAX_TEAL_VERSION,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
    Global,
    OnCompleteAction,
    OptimizeOptions,
    Router,
    Bytes,
    Approve,
)

from beaker.decorators import (
    get_handler_config,
    MethodHints,
    MethodConfig,
    create,
)

from beaker.state import (
    AccountState,
    AccountStateBlob,
    ApplicationStateBlob,
    ApplicationState,
    DynamicAccountStateValue,
    AccountStateValue,
    ApplicationStateValue,
    DynamicApplicationStateValue,
)
from beaker.errors import BareOverwriteError
from beaker.precompile import Precompile


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
            for m in sorted(list(set(dir(self.__class__)) - set(dir(super()))))
            if not m.startswith("__")
        }

        # Initialize these ahead of time, may not
        # be set after init if len(precompiles)>0
        self.approval_program = None
        self.clear_program = None

        self.on_create = None
        self.on_update = None
        self.on_delete = None
        self.on_opt_in = None
        self.on_close_out = None
        self.on_clear_state = None

        self.hints: dict[str, MethodHints] = {}
        self.bare_externals: dict[str, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, Optional[MethodConfig]]] = {}
        self.precompiles: dict[str, Precompile] = {}

        acct_vals: dict[
            str, AccountStateValue | DynamicAccountStateValue | AccountStateBlob
        ] = {}
        app_vals: dict[
            str,
            ApplicationStateValue | DynamicApplicationStateValue | ApplicationStateBlob,
        ] = {}

        for name, (bound_attr, static_attr) in self.attrs.items():
            # Check for state vals
            match bound_attr:

                case AccountStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    acct_vals[name] = bound_attr
                case DynamicAccountStateValue():
                    acct_vals[name] = bound_attr
                case AccountStateBlob():
                    acct_vals[name] = bound_attr

                case ApplicationStateBlob():
                    app_vals[name] = bound_attr
                case ApplicationStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    app_vals[name] = bound_attr
                case DynamicApplicationStateValue():
                    app_vals[name] = bound_attr

                case Precompile():
                    self.precompiles[name] = bound_attr

            # Already dealt with these, move on
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

                self.methods[name] = (abi_meth, handler_config.method_config)

                if handler_config.is_create():
                    if self.on_create is not None:
                        raise TealInputError("Multiple create methods specified")
                    self.on_create = static_attr

                if handler_config.is_update():
                    if self.on_update is not None:
                        raise TealInputError("Multiple update methods specified")
                    self.on_update = static_attr

                if handler_config.is_delete():
                    if self.on_delete is not None:
                        raise TealInputError("Multiple delete methods specified")
                    self.on_delete = static_attr

                if handler_config.is_opt_in():
                    if self.on_opt_in is not None:
                        raise TealInputError("Multiple opt in methods specified")
                    self.on_opt_in = static_attr

                if handler_config.is_clear_state():
                    if self.on_clear_state is not None:
                        raise TealInputError("Multiple clear state methods specified")
                    self.on_clear_state = static_attr

                if handler_config.is_close_out():
                    if self.on_close_out is not None:
                        raise TealInputError("Multiple close out methods specified")
                    self.on_close_out = static_attr

                self.methods[name] = (abi_meth, handler_config.method_config)
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

        # If there are no precompiles, we can build the programs
        # with what we already have
        if len(self.precompiles) == 0:
            self.compile()

    def compile(self):

        # TODO: reset router?
        # It will fail if compile is re-called but we shouldn't rely on that

        # Add method externals
        for _, method_tuple in self.methods.items():
            method, method_config = method_tuple
            self.router.add_method_handler(
                method_call=method, method_config=method_config
            )

        # Compile approval and clear programs
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

        if self.approval_program is None or self.clear_program is None:
            raise Exception(
                "approval or clear program are none, please build the programs first"
            )

        return {
            "hints": {k: v.dictify() for k, v in self.hints.items() if not v.empty()},
            "source": {
                "approval": base64.b64encode(self.approval_program.encode()).decode(
                    "utf8"
                ),
                "clear": base64.b64encode(self.clear_program.encode()).decode("utf8"),
            },
            "schema": {
                "local": self.acct_state.dictify(),
                "global": self.app_state.dictify(),
            },
            "contract": self.contract.dictify(),
        }

    def initialize_application_state(self) -> Expr:
        """
        Initialize any application state variables declared

        :return: The Expr to initialize the application state.
        :rtype: pyteal.Expr
        """
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
        return Approve()
