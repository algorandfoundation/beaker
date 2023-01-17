import base64
import dataclasses
import itertools
import json
import typing
from functools import partialmethod
from pathlib import Path
from typing import (
    Any,
    cast,
    Optional,
    Callable,
    TypeAlias,
    Literal,
    ParamSpec,
    Concatenate,
    TypeVar,
    overload,
    Generic,
)

from algosdk.abi import Method, Contract
from algosdk.v2client.algod import AlgodClient
from pyteal import (
    SubroutineFnWrapper,
    Txn,
    MAX_TEAL_VERSION,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
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
    HandlerFunc,
    _authorize,
    _capture_structs_and_defaults,
    HandlerConfig,
)
from beaker.errors import BareOverwriteError
from beaker.precompile import AppPrecompile, LSigPrecompile
from beaker.state import AccountState, ApplicationState

if typing.TYPE_CHECKING:
    from beaker.logic_signature import LogicSignature


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


@dataclasses.dataclass
class ABIExternal:
    actions: dict[OnCompleteActionName, CallConfig]
    method: ABIReturnSubroutine
    hints: MethodHints


DecoratorReturnType: TypeAlias = (
    SubroutineFnWrapper
    | Callable[[HandlerFunc], SubroutineFnWrapper]
    | ABIReturnSubroutine
    | Callable[[HandlerFunc], ABIReturnSubroutine]
)


class StateType(type):
    def __new__(mcs, name: str, bases: tuple[type], dct: dict[str, Any]) -> "StateType":
        collect_keys = ["_acct_vals", "_app_vals", "_precompiles"]
        for key in collect_keys:
            dct[key] = {}
        for base in bases:
            if issubclass(base, Application):
                for key in collect_keys:
                    dct[key].update(getattr(base, key, {}))
        cls = super().__new__(mcs, name, bases, dct)
        return cls


class State(metaclass=StateType):
    pass


TState = TypeVar("TState", bound=State)


class Application(Generic[TState]):
    """Application contains logic to detect State Variables, Bare methods
    ABI Methods and internal subroutines.

    It should be subclassed to provide basic behavior to a custom application.
    """

    def __init__(
        self,
        state: TState,
        teal_version: int = MAX_TEAL_VERSION,
        unconditional_create_approval: bool = True,
    ):
        """Initialize the Application, finding all the custom attributes and initializing the Router"""
        self.teal_version = teal_version
        self._state = state
        self._compiled: CompiledApplication | None = None
        self._bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self._lsig_precompiles: dict[LogicSignature, LSigPrecompile] = {}
        self._app_precompiles: dict[Application, AppPrecompile] = {}
        self._abi_externals: dict[str, ABIExternal] = {}
        self.acct_state = AccountState(klass=state.__class__)
        self.app_state = ApplicationState(klass=state.__class__)

        if unconditional_create_approval:

            @self.create
            def create() -> Expr:
                return Approve()

    @property
    def state(self) -> TState:
        return self._state

    @overload
    def precompile(self, value: "Application", /) -> AppPrecompile:
        ...

    @overload
    def precompile(self, value: "LogicSignature", /) -> LSigPrecompile:
        ...

    def precompile(
        self, value: "Application | LogicSignature", /, *, _: None = None
    ) -> AppPrecompile | LSigPrecompile:
        match value:
            case Application() as app:
                return self._app_precompiles.setdefault(app, AppPrecompile(app))
            case LogicSignature() as lsig:
                return self._lsig_precompiles.setdefault(lsig, LSigPrecompile(lsig))
            case _:
                raise TypeError()

    @property
    def precompiles(self) -> list[AppPrecompile | LSigPrecompile]:
        return list(
            itertools.chain(
                self._app_precompiles.values(),
                self._lsig_precompiles.values(),
            )
        )

    @property
    def hints(self) -> dict[str, MethodHints]:
        return {ext.method.name(): ext.hints for ext in self._abi_externals.values()}

    def register_abi_external(
        self,
        method: ABIReturnSubroutine,
        *,
        actions: dict[OnCompleteActionName, CallConfig],
        hints: MethodHints,
        override: bool | None,
    ) -> None:
        if any(cc == CallConfig.NEVER for cc in actions.values()):
            raise ValueError("???")
        method_sig = method.method_signature()
        if override is True:
            if method_sig not in self._abi_externals:
                raise ValueError("override=True, but nothing to override")
            # TODO: should we warn if call config differs?
        elif override is False:
            if method_sig in self._abi_externals:
                raise ValueError(
                    "override=False, but method with matching signature already registered"
                )
        self._abi_externals[method_sig] = ABIExternal(
            actions=actions,
            method=method,
            hints=hints,
        )

    def register_bare_external(
        self,
        sub: SubroutineFnWrapper,
        *,
        for_action: OnCompleteActionName,
        call_config: CallConfig,
        override: bool | None,
    ) -> None:
        if call_config == CallConfig.NEVER:
            raise ValueError("???")
        if override is True:
            if for_action not in self._bare_externals:
                raise ValueError("override=True, but nothing to override")
        elif override is False:
            if for_action in self._bare_externals:
                raise BareOverwriteError(for_action)

        self._bare_externals[for_action] = OnCompleteAction(
            action=sub, call_config=call_config
        )

    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> SubroutineFnWrapper:
        ...

    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: Literal[False] = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine:
        ...

    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> SubroutineFnWrapper | ABIReturnSubroutine:
        ...

    @overload
    def external(
        self,
        fn: None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> Callable[[HandlerFunc], SubroutineFnWrapper]:
        ...

    @overload
    def external(
        self,
        fn: None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: Literal[False] = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> Callable[[HandlerFunc], ABIReturnSubroutine]:
        ...

    @overload
    def external(
        self,
        fn: None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> Callable[[HandlerFunc], SubroutineFnWrapper] | Callable[
        [HandlerFunc], ABIReturnSubroutine
    ]:
        ...

    def external(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorReturnType:
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

        if bare and read_only:
            raise ValueError("read_only has no effect on bare methods")

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

        decorator: DecoratorReturnType
        if bare:

            def decorator(func: HandlerFunc) -> SubroutineFnWrapper:
                if authorize is not None:
                    func = _authorize(authorize)(func)
                sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)
                if sub.subroutine.argument_count():
                    raise TypeError("Bare externals must take no method arguments")
                for for_action, call_config in actions.items():
                    self.register_bare_external(
                        sub,
                        for_action=for_action,
                        call_config=call_config,
                        override=override,
                    )
                return sub

        else:

            def decorator(func: HandlerFunc) -> ABIReturnSubroutine:
                if authorize is not None:
                    func = _authorize(authorize)(func)
                method = ABIReturnSubroutine(func, overriding_name=name)
                conf = HandlerConfig(read_only=read_only)
                _capture_structs_and_defaults(func, conf)
                hints = conf.hints()
                self.register_abi_external(
                    method, actions=actions, hints=hints, override=override
                )
                return method

        if fn is None:
            return decorator

        return decorator(fn)

    def _shortcut_external(
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
        override: bool | None = False,
    ) -> DecoratorReturnType:
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

    def create(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool = True,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorReturnType:
        return self._shortcut_external(
            fn,
            action="no_op",
            allow_call=allow_call,
            allow_create=True,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )

    # TODO: expand all these - will be more verbose but likely play better with type hints
    delete = partialmethod(_shortcut_external, action="delete")
    update = partialmethod(_shortcut_external, action="update")
    opt_in = partialmethod(_shortcut_external, action="opt_in")
    clear_state = partialmethod(_shortcut_external, action="clear_state")
    close_out = partialmethod(_shortcut_external, action="close_out")
    no_op = partialmethod(_shortcut_external, action="no_op")

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
            for precompile in self.precompiles:
                precompile.compile(client)

            bare_call_kwargs = {str(k): v for k, v in self._bare_externals.items()}
            router = Router(
                name=self.__class__.__name__,
                bare_calls=BareCallActions(**bare_call_kwargs),
                descr=self.__doc__,
            )

            # Add method externals
            for abi_external in self._abi_externals.values():
                router.add_method_handler(
                    method_call=abi_external.method,
                    method_config=MethodConfig(
                        **{str(a): cc for a, cc in abi_external.actions.items()}
                    ),
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
