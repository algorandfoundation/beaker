import base64
from inspect import getattr_static
from typing import Final, Any, cast, Optional
from algosdk.v2client.algod import AlgodClient
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
    HandlerFunc,
)

from beaker.state import (
    AccountState,
    AccountStateBlob,
    ApplicationStateBlob,
    ApplicationState,
    ReservedAccountStateValue,
    AccountStateValue,
    ApplicationStateValue,
    ReservedApplicationStateValue,
    prefix_key_gen,
)
from beaker.errors import BareOverwriteError
from beaker.precompile import AppPrecompile, LSigPrecompile
from beaker.lib.storage import List


def get_method_spec(fn: HandlerFunc) -> Method:
    hc = get_handler_config(fn)
    if hc.method_spec is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.method_spec


def get_method_signature(fn: HandlerFunc) -> str:
    return get_method_spec(fn).get_signature()


def get_method_selector(fn: HandlerFunc) -> bytes:
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

        # Get initial list of all attrs declared
        initial_attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in sorted(list(set(dir(self.__class__)) - set(dir(super()))))
            if not m.startswith("__")
        }

        # Make sure we preserve the ordering of declaration
        ordering = [
            m for m in list(vars(self.__class__).keys()) if not m.startswith("__")
        ]
        self.attrs = {k: initial_attrs[k] for k in ordering} | initial_attrs

        # Initialize these ahead of time, may not
        # be set after init if len(precompiles)>0
        self.approval_program: Optional[str] = None
        self.clear_program: Optional[str] = None

        all_creates = []
        all_updates = []
        all_deletes = []
        all_opt_ins = []
        all_close_outs = []
        all_clear_states = []

        self.hints: dict[str, MethodHints] = {}
        self.bare_externals: dict[str, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, Optional[MethodConfig]]] = {}
        self.precompiles: dict[str, AppPrecompile | LSigPrecompile] = {}

        acct_vals: dict[
            str, AccountStateValue | ReservedAccountStateValue | AccountStateBlob
        ] = {}
        app_vals: dict[
            str,
            ApplicationStateValue
            | ReservedApplicationStateValue
            | ApplicationStateBlob,
        ] = {}

        for name, (bound_attr, static_attr) in self.attrs.items():
            # Check for state vals
            match bound_attr:

                # Account state
                case AccountStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    acct_vals[name] = bound_attr
                case ReservedAccountStateValue():
                    if bound_attr.key_generator is None:
                        bound_attr.set_key_gen(prefix_key_gen(name))
                    acct_vals[name] = bound_attr
                case AccountStateBlob():
                    acct_vals[name] = bound_attr

                # App state
                case ApplicationStateBlob():
                    app_vals[name] = bound_attr
                case ApplicationStateValue():
                    if bound_attr.key is None:
                        bound_attr.key = Bytes(name)
                    app_vals[name] = bound_attr
                case ReservedApplicationStateValue():
                    if bound_attr.key_generator is None:
                        bound_attr.set_key_gen(prefix_key_gen(name))
                    app_vals[name] = bound_attr

                # Precompiles
                case LSigPrecompile() | AppPrecompile():
                    self.precompiles[name] = bound_attr

                # Boxes
                case List():
                    if bound_attr.name is None:
                        bound_attr.name = Bytes(name)

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
            elif handler_config.method_spec is not None and not handler_config.internal:
                # Create the ABIReturnSubroutine from the static attr
                # but override the implementation with the bound version
                abi_meth = ABIReturnSubroutine(
                    static_attr, overriding_name=handler_config.method_spec.name
                )

                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

                self.methods[name] = (abi_meth, handler_config.method_config)

                if handler_config.is_create():
                    all_creates.append(static_attr)
                if handler_config.is_update():
                    all_updates.append(static_attr)
                if handler_config.is_delete():
                    all_deletes.append(static_attr)
                if handler_config.is_opt_in():
                    all_opt_ins.append(static_attr)
                if handler_config.is_clear_state():
                    all_clear_states.append(static_attr)
                if handler_config.is_close_out():
                    all_close_outs.append(static_attr)

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

        self.on_create = all_creates.pop() if len(all_creates) == 1 else None
        self.on_update = all_updates.pop() if len(all_updates) == 1 else None
        self.on_delete = all_deletes.pop() if len(all_deletes) == 1 else None
        self.on_opt_in = all_opt_ins.pop() if len(all_opt_ins) == 1 else None
        self.on_close_out = all_close_outs.pop() if len(all_close_outs) == 1 else None
        self.on_clear_state = (
            all_clear_states.pop() if len(all_clear_states) == 1 else None
        )

        self.acct_state = AccountState(acct_vals)
        self.app_state = ApplicationState(app_vals)

        # If there are no precompiles, we can build the programs
        # with what we already have and don't need to pass an
        # algod client
        if len(self.precompiles) == 0:
            self.compile()

    def compile(self, client: Optional[AlgodClient] = None) -> tuple[str, str]:
        """Fully compile the application to TEAL

        Note: If the application has ``Precompile`` fields, the ``client`` must be passed to
        compile them into bytecode.

        Args:
            client (optional): An Algod client that can be passed to ``Precompile`` to have them fully compiled.
        """
        if self.approval_program is not None and self.clear_program is not None:
            return self.approval_program, self.clear_program

        if len(self.precompiles) > 0:
            # make sure all the precompiles are available
            for precompile in self.precompiles.values():
                precompile.compile(client)  # type: ignore

        self.router = Router(
            name=self.__class__.__name__,
            bare_calls=BareCallActions(**self.bare_externals),
            descr=self.__doc__,
        )

        # Add method externals
        for _, method_tuple in self.methods.items():
            method, method_config = method_tuple
            self.router.add_method_handler(
                method_call=method,
                method_config=method_config,
                overriding_name=method.name(),
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

        return self.approval_program, self.clear_program

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

    def initialize_account_state(self, addr: Expr = Txn.sender()) -> Expr:
        """
        Initialize any account state variables declared

        :param addr: Optional, address of account to initialize state for.
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """

        return self.acct_state.initialize(addr)

    @create
    def create(self) -> Expr:
        """create is the only handler defined by default and only approves the transaction.

        Override this method to define custom behavior.
        """
        return Approve()

    def dump(self, directory: str = ".", client: Optional[AlgodClient] = None) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory (optional): str path to the directory where the artifacts should be written
            client (optional): AlgodClient to be passed to any precompiles
        """
        if self.approval_program is None:
            if len(self.precompiles) > 0 and client is None:
                raise Exception(
                    "Approval program empty, if you have precompiles, pass an Algod client to build the precompiles"
                )
            self.compile(client)

        import json
        import os

        if not os.path.exists(directory):
            os.mkdir(directory)

        with open(os.path.join(directory, "approval.teal"), "w") as f:
            if self.approval_program is None:
                raise Exception("Approval program empty")
            f.write(self.approval_program)

        with open(os.path.join(directory, "clear.teal"), "w") as f:
            if self.clear_program is None:
                raise Exception("Clear program empty")
            f.write(self.clear_program)

        with open(os.path.join(directory, "contract.json"), "w") as f:
            if self.contract is None:
                raise Exception("Contract empty")
            f.write(json.dumps(self.contract.dictify(), indent=4))

        with open(os.path.join(directory, "application.json"), "w") as f:
            f.write(json.dumps(self.application_spec(), indent=4))
