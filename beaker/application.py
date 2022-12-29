import base64
import dataclasses
import json
from inspect import getattr_static
from typing import Final, Any, cast, Optional
from pathlib import Path

from algosdk.v2client.algod import AlgodClient
from algosdk.abi import Method, Contract
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

        self._compiled: CompiledApplication | None = None

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
                    if bound_attr.key_gen is None:
                        bound_attr.key_gen = prefix_key_gen(name)
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
                    if bound_attr.key_gen is None:
                        bound_attr.key_gen = prefix_key_gen(name)
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
                for oc, action in handler_config.bare_method.__dict__.items():
                    action = cast(OnCompleteAction, action)
                    if action.is_empty():
                        continue
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
        if not self.precompiles:
            self.compile()

    def compile(self, client: Optional[AlgodClient] = None) -> tuple[str, str]:
        """Fully compile the application to TEAL

        Note: If the application has ``Precompile`` fields, the ``client`` must be passed to
        compile them into bytecode.

        Args:
            client (optional): An Algod client that can be passed to ``Precompile`` to have them fully compiled.
        """
        if self._compiled is None:

            # make sure all the precompiles are available
            for precompile in self.precompiles.values():
                precompile.compile(client)

            router = Router(
                name=self.__class__.__name__,
                bare_calls=BareCallActions(**self.bare_externals),
                descr=self.__doc__,
            )

            # Add method externals
            for _, method_tuple in self.methods.items():
                method, method_config = method_tuple
                router.add_method_handler(
                    method_call=method,
                    method_config=method_config,
                    overriding_name=method.name(),
                )

            # Compile approval and clear programs
            (approval_program, clear_program, contract,) = router.compile_program(
                version=self.teal_version,
                assemble_constants=True,
                optimize=OptimizeOptions(scratch_slots=True),
            )

            application_spec = {
                "hints": {
                    k: v.dictify() for k, v in self.hints.items() if not v.empty()
                },
                "source": {
                    "approval": base64.b64encode(approval_program.encode()).decode(
                        "utf8"
                    ),
                    "clear": base64.b64encode(clear_program.encode()).decode("utf8"),
                },
                "schema": {
                    "local": self.acct_state.dictify(),
                    "global": self.app_state.dictify(),
                },
                "contract": contract.dictify(),
            }

            self._compiled = CompiledApplication(
                approval_program=approval_program,
                clear_program=clear_program,
                contract=contract,
                application_spec=application_spec,
            )

        return self._compiled.approval_program, self._compiled.clear_program

    @property
    def approval_program(self) -> str | None:
        if self._compiled is None:
            return None
        return self._compiled.approval_program

    @property
    def clear_program(self) -> str | None:
        if self._compiled is None:
            return None
        return self._compiled.clear_program

    @property
    def contract(self) -> Contract | None:
        if self._compiled is None:
            return None
        return self._compiled.contract

    def application_spec(self) -> dict[str, Any]:
        """returns a dictionary, helpful to provide to callers with information about the application specification"""
        if self._compiled is None:
            raise ValueError(
                "approval or clear program are none, please build the programs first"
            )
        return self._compiled.application_spec

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
        if self._compiled is None:
            if self.precompiles and client is None:
                raise ValueError(
                    "Approval program empty, if you have precompiles, pass an Algod client to build the precompiles"
                )
            self.compile(client)

        assert self._compiled is not None
        self._compiled.dump(Path(directory))


@dataclasses.dataclass
class CompiledApplication:
    approval_program: str
    clear_program: str
    contract: Contract
    application_spec: dict[str, Any]

    def dump(self, directory: Path) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory: path to the directory where the artifacts should be written
        """
        directory.mkdir(exist_ok=True)

        (directory / "approval.teal").write_text(self.approval_program)
        (directory / "clear.teal").write_text(self.clear_program)
        (directory / "contract.json").write_text(
            json.dumps(self.contract.dictify(), indent=4)
        )
        (directory / "application.json").write_text(
            json.dumps(self.application_spec, indent=4)
        )
