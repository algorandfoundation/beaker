import base64
import dataclasses
import json
from functools import partialmethod, partial
from inspect import getattr_static
from pathlib import Path
from typing import (
    Final,
    Any,
    cast,
    Optional,
    Callable,
    TypeAlias,
    Literal,
    ParamSpec,
    Concatenate,
    TypeVar,
)

from algosdk.abi import Method, Contract
from algosdk.v2client.algod import AlgodClient
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
    Approve,
    CallConfig,
    TealType,
)

from beaker.decorators import (
    get_handler_config,
    MethodHints,
    MethodConfig,
    create,
    HandlerFunc,
    ABIExternalMetadata,
    _authorize,
)
from beaker.errors import BareOverwriteError
from beaker.precompile import AppPrecompile, LSigPrecompile
from beaker.state import AccountState, ApplicationState
from beaker.utils import get_class_attributes


def get_method_spec(fn: HandlerFunc) -> Method:
    hc = get_handler_config(fn)
    if hc.method_spec is None:
        raise Exception("Expected argument to be an ABI method")
    return hc.method_spec


def get_method_signature(fn: HandlerFunc) -> str:
    return get_method_spec(fn).get_signature()


def get_method_selector(fn: HandlerFunc) -> bytes:
    return get_method_spec(fn).get_selector()


OnCompleteActionName: TypeAlias = Literal[
    "no_op",
    "opt_in",
    "close_out",
    "clear_state",
    "update_application",
    "delete_application",
]

Self = TypeVar("Self", bound="Application")
T = TypeVar("T")
P = ParamSpec("P")


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

        all_creates = []
        all_updates = []
        all_deletes = []
        all_opt_ins = []
        all_close_outs = []
        all_clear_states = []

        self.hints: dict[str, MethodHints] = {}
        self.bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self.methods: dict[str, tuple[ABIReturnSubroutine, Optional[MethodConfig]]] = {}
        self.precompiles: dict[str, AppPrecompile | LSigPrecompile] = {}

        self._abi_externals: dict[HandlerFunc, list[ABIExternalMetadata]] = {}

        for name in get_class_attributes(self.__class__, use_legacy_ordering=True):
            bound_attr = getattr(self, name)
            static_attr = getattr_static(self, name)
            match bound_attr:
                # Precompiles
                case LSigPrecompile() | AppPrecompile():
                    self.precompiles[name] = bound_attr
                    continue

            # Check for externals and internal methods
            handler_config = get_handler_config(bound_attr)

            # Bare externals
            if handler_config.bare_method is not None:
                for oc, action in handler_config.bare_method.__dict__.items():
                    oc = cast(OnCompleteActionName, oc)
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
            elif handler_config.method_spec is not None:
                # Create the ABIReturnSubroutine from the static attr
                # but override the implementation with the bound version
                abi_meth = ABIReturnSubroutine(
                    static_attr, overriding_name=handler_config.method_spec.name
                )

                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

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

        self.on_create = all_creates.pop() if len(all_creates) == 1 else None
        self.on_update = all_updates.pop() if len(all_updates) == 1 else None
        self.on_delete = all_deletes.pop() if len(all_deletes) == 1 else None
        self.on_opt_in = all_opt_ins.pop() if len(all_opt_ins) == 1 else None
        self.on_close_out = all_close_outs.pop() if len(all_close_outs) == 1 else None
        self.on_clear_state = (
            all_clear_states.pop() if len(all_clear_states) == 1 else None
        )

        self.acct_state = AccountState(klass=self.__class__)
        self.app_state = ApplicationState(klass=self.__class__)

    def register_abi_external(
        self,
        fn: HandlerFunc | SubroutineFnWrapper,
        *,
        for_action: OnCompleteActionName,
        call_config: CallConfig,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        read_only: bool = False,
        override: bool = False,
    ):
        self._abi_externals.setdefault(fn, []).append(
            ABIExternalMetadata(
                method_config=MethodConfig(**{str(for_action): call_config}),
                name_override=name,
                authorize=authorize,
                read_only=read_only,
            )
        )

    def register_bare_external(
        self,
        fn_or_sub: HandlerFunc | SubroutineFnWrapper,
        *,
        for_action: OnCompleteActionName,
        call_config: CallConfig,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        override: bool = False,
    ):
        if call_config == CallConfig.NEVER:
            raise ValueError("???")
        if override:
            if for_action not in self.bare_externals:
                raise ValueError("override=True, but nothing to override")
        else:
            if for_action in self.bare_externals:
                raise BareOverwriteError(for_action)
        if isinstance(fn_or_sub, SubroutineFnWrapper):
            sub = fn_or_sub
            if authorize is not None:
                func = sub.subroutine.implementation
                func = _authorize(authorize)(func)
                sub = SubroutineFnWrapper(
                    func,
                    return_type=sub.subroutine.return_type,
                    name=sub.subroutine.name(),
                )
        else:
            func = fn_or_sub
            if authorize is not None:
                func = _authorize(authorize)(func)
            sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)

        if sub.subroutine.argument_count():
            raise TypeError("Bare externals must take no method arguments")
        self.bare_externals[for_action] = OnCompleteAction(
            action=sub, call_config=call_config
        )

    def external(
        self,
        fn: HandlerFunc | SubroutineFnWrapper | None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool = False,
    ) -> HandlerFunc | Callable[..., HandlerFunc]:
        """
        Add the method decorated to be handled as an ABI method for the Application

        Args:
            fn: The function being wrapped.
            method_config:  <TODO>
            name: Name of ABI method. If not set, name of the python method will be used.
                Useful for method overriding.
            authorize: a subroutine with input of ``Txn.sender()`` and output uint64
                interpreted as allowed if the output>0.
            bare:
            read_only: Mark a method as callable with no fee using dryrun or simulate
            override:

        Returns:
            The original method with additional elements set in it's
            :code:`__handler_config__` attribute
        """

        actions: dict[OnCompleteActionName, CallConfig]
        match method_config:
            case None:
                if bare:
                    raise ValueError("bare requires method_config")
                else:
                    actions = {"no_op": CallConfig.CALL}
            case MethodConfig():
                actions = {
                    cast(OnCompleteActionName, key): value
                    for key, value in method_config.__dict__.items()
                    if value != CallConfig.NEVER
                }
            case _:
                actions = method_config

        if bare:
            if read_only:
                raise ValueError("read_only has no effect on bare methods")
            register = partial(
                self.register_bare_external,
                name=name,
                authorize=authorize,
                override=override,
            )
        else:
            register = partial(
                self.register_abi_external,
                name=name,
                authorize=authorize,
                read_only=read_only,
                override=override,
            )

        def _impl(
            f: HandlerFunc | SubroutineFnWrapper,
        ) -> HandlerFunc | SubroutineFnWrapper:
            for for_action, call_config in actions.items():
                register(f, for_action=for_action, call_config=call_config)
            return f

        if fn is None:
            return _impl

        return _impl(fn)

    def create_(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        action: OnCompleteActionName = "no_op",
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool = False,
    ) -> HandlerFunc | Callable[..., HandlerFunc]:
        return self.external(
            fn,
            method_config={action: CallConfig.ALL if allow_call else CallConfig.CREATE},
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )

    def _named_external(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        action: OnCompleteActionName,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool = False,
    ) -> HandlerFunc | Callable[..., HandlerFunc]:
        if allow_call and allow_create:
            call_config = CallConfig.ALL
        elif allow_call:
            call_config = CallConfig.CALL
        elif allow_create:
            call_config = CallConfig.CREATE
        else:
            raise ValueError("Require one of allow_call or allow_create to be True")
        return self.external(
            fn,
            method_config={action: call_config},
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )

    # TODO: expand all these - will be more verbose but likely play better with type hints
    delete = partialmethod(_named_external, action="delete")
    update = partialmethod(_named_external, action="update")
    opt_in = partialmethod(_named_external, action="opt_in")
    clear_state = partialmethod(_named_external, action="clear_state")
    close_out = partialmethod(_named_external, action="close_out")
    no_op = partialmethod(_named_external, action="no_op")

    def implement(
        self: Self,
        blueprint: Callable[Concatenate[Self, P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        return blueprint(self, *args, **kwargs)

    def compile(self, client: Optional[AlgodClient] = None) -> tuple[str, str]:
        """Fully compile the application to TEAL

        Note: If the application has ``Precompile`` fields, the ``client`` must be passed to
        compile them into bytecode.

        Args:
            client (optional): An Algod client that can be passed to ``Precompile`` to have them fully compiled.
        """
        # TODO: verify no overlap of BCA with ABI

        if self._compiled is None:

            # make sure all the precompiles are available
            for precompile in self.precompiles.values():
                precompile.compile(client)

            bare_call_kwargs = {str(k): v for k, v in self.bare_externals.items()}
            router = Router(
                name=self.__class__.__name__,
                bare_calls=BareCallActions(**bare_call_kwargs),
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
            approval_program, clear_program, contract = router.compile_program(
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

    @create(bare=True)
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
