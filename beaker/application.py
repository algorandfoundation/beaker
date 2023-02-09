import dataclasses
import inspect
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import (
    cast,
    Optional,
    Callable,
    TypeAlias,
    Literal,
    ParamSpec,
    Concatenate,
    TypeVar,
    overload,
    Iterator,
    Generic,
    MutableMapping,
)

from algosdk.v2client.algod import AlgodClient
from pyteal import (
    SubroutineFnWrapper,
    Txn,
    MAX_PROGRAM_VERSION,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
    OnCompleteAction,
    OptimizeOptions,
    Router,
    CallConfig,
    TealType,
    MethodConfig,
)

from beaker.application_specification import ApplicationSpecification
from beaker.decorators import (
    MethodHints,
    HandlerFunc,
    capture_method_hints_and_remove_defaults,
)
from beaker.decorators.authorize import _authorize
from beaker.logic_signature import LogicSignature, LogicSignatureTemplate
from beaker.precompile import AppPrecompile, LSigPrecompile, LSigTemplatePrecompile
from beaker.state import AccountState, ApplicationState

OnCompleteActionName: TypeAlias = Literal[
    "no_op",
    "opt_in",
    "close_out",
    "update_application",
    "delete_application",
]

T = TypeVar("T")
P = ParamSpec("P")
TState = TypeVar("TState", covariant=True)


@dataclasses.dataclass
class ABIExternal:
    actions: dict[OnCompleteActionName, CallConfig]
    method: ABIReturnSubroutine
    hints: MethodHints


DecoratorResultType: TypeAlias = SubroutineFnWrapper | ABIReturnSubroutine
DecoratorFuncType: TypeAlias = Callable[[HandlerFunc], DecoratorResultType]


@dataclasses.dataclass(frozen=True)
class CompileContext:
    app: "Application" = dataclasses.field(kw_only=True)
    client: AlgodClient | None


_ctx: ContextVar[CompileContext] = ContextVar("beaker.compile_context")


@contextmanager
def _set_ctx(app: "Application", client: AlgodClient | None) -> Iterator[None]:
    token = _ctx.set(CompileContext(app=app, client=client))
    try:
        yield
    finally:
        _ctx.reset(token)


@dataclasses.dataclass(kw_only=True)
class CompilerOptions:
    avm_version: int = MAX_PROGRAM_VERSION
    """avm_version: defines the #pragma version used in output"""
    scratch_slots: bool = True
    """scratch_slots: cancel contiguous store/load operations that have no load dependencies elsewhere. 
       default=True"""
    frame_pointers: bool | None = None
    """frame_pointers: employ frame pointers instead of scratch slots during compilation.
       Available and enabled by default from AVM version 8"""
    assemble_constants: bool = True
    """assembleConstants: When true, the compiler will produce a program with fully
        assembled constants, rather than using the pseudo-ops `int`, `byte`, and `addr`. These
        constants will be assembled in the most space-efficient way, so enabling this may reduce
        the compiled program's size. Enabling this option requires a minimum AVM version of 3.
        Defaults to True."""


class Application(Generic[TState]):
    @overload
    def __init__(
        self: "Application[None]",
        name: str,
        *,
        descr: str | None = None,
        compiler_options: CompilerOptions | None = None,
    ):
        ...

    @overload
    def __init__(
        self: "Application[TState]",
        name: str,
        *,
        state: TState,
        descr: str | None = None,
        compiler_options: CompilerOptions | None = None,
    ):
        ...

    def __init__(
        self,
        name: str,
        *,
        state: TState = cast(TState, None),
        descr: str | None = None,
        compiler_options: CompilerOptions | None = None,
    ):
        """<TODO>"""
        self._state: TState = state
        self.name = name
        self.descr = descr
        self.compiler_options = compiler_options or CompilerOptions()
        self.bare_methods: dict[str, SubroutineFnWrapper] = {}
        self.abi_methods: dict[str, ABIReturnSubroutine] = {}

        self._bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self._clear_state_method: SubroutineFnWrapper | None = None
        self._lsig_precompiles: dict[LogicSignature, LSigPrecompile] = {}
        self._lsig_template_precompiles: dict[
            LogicSignatureTemplate, LSigTemplatePrecompile
        ] = {}
        self._app_precompiles: dict[Application, AppPrecompile] = {}
        self._abi_externals: dict[str, ABIExternal] = {}
        self._acct_state = AccountState(self._state)
        self._app_state = ApplicationState(self._state)

    def __init_subclass__(cls) -> None:
        warnings.warn(
            "Subclassing beaker.Application is deprecated, please see the migration guide at: TODO",
            DeprecationWarning,
        )

    @property
    def state(self) -> TState:
        if ctx := _ctx.get(None):
            # if inside a context (ie when an expression is being evaluated by PyTeal),
            # raise a warning when attempting to access the state of a different app instance
            if ctx.app is not self:
                warnings.warn(
                    f"Accessing state property of Application {ctx.app.name} during compilation of Application {self.name}",
                    RuntimeWarning,
                )
        return self._state

    @overload
    def precompiled(self, value: "Application", /) -> AppPrecompile:
        ...

    @overload
    def precompiled(self, value: "LogicSignature", /) -> LSigPrecompile:
        ...

    @overload
    def precompiled(self, value: "LogicSignatureTemplate", /) -> LSigTemplatePrecompile:
        ...

    def precompiled(
        self,
        value: "Application | LogicSignature | LogicSignatureTemplate",
        /,
    ) -> AppPrecompile | LSigPrecompile | LSigTemplatePrecompile:
        try:
            ctx = _ctx.get()
        except LookupError:
            raise LookupError("precompiled(...) should be called inside a function")
        if ctx.app is not self:
            raise ValueError("precompiled() used in another apps context")
        if ctx.client is None:
            raise ValueError(
                "beaker.precompiled(...) requires use of a client when calling Application.compile(...)"
            )
        match value:
            case Application() as app:
                # TODO: check recursion?
                return self._app_precompiles.setdefault(
                    app, AppPrecompile(app, ctx.client)
                )
            case LogicSignature() as lsig:
                return self._lsig_precompiles.setdefault(
                    lsig, LSigPrecompile(lsig, ctx.client)
                )
            case LogicSignatureTemplate() as lsig_template:
                return self._lsig_template_precompiles.setdefault(
                    lsig_template, LSigTemplatePrecompile(lsig_template, ctx.client)
                )
            case _:
                raise TypeError("TODO write error message")

    def register_abi_external(
        self,
        method: ABIReturnSubroutine,
        *,
        python_func_name: str,
        actions: dict[OnCompleteActionName, CallConfig],
        hints: MethodHints,
        override: bool | None,
    ) -> None:
        if any(cc == CallConfig.NEVER for cc in actions.values()):
            raise ValueError("???")
        method_sig = method.method_signature()
        existing_method = self._abi_externals.get(method_sig)
        if existing_method is None:
            if override is True:
                raise ValueError("override=True, but nothing to override")
        else:
            if override is False:
                raise ValueError(
                    "override=False, but method with matching signature already registered"
                )
            # TODO: should we warn if call config differs?
            self.deregister_abi_method(existing_method.method)
        self._abi_externals[method_sig] = ABIExternal(
            actions=actions,
            method=method,
            hints=hints,
        )
        self.abi_methods[python_func_name] = method

    def deregister_abi_method(
        self,
        name_or_reference: str | ABIReturnSubroutine,
        /,
    ) -> None:
        if isinstance(name_or_reference, str):
            method = self.abi_methods.pop(name_or_reference)
        else:
            method = name_or_reference
            _remove_first_match(self.abi_methods, lambda _, v: v is method)
        _remove_first_match(self._abi_externals, lambda _, v: v.method is method)

    def register_bare_external(
        self,
        sub: SubroutineFnWrapper,
        *,
        python_func_name: str,
        actions: dict[OnCompleteActionName, CallConfig],
        override: bool | None,
    ) -> None:
        for for_action, call_config in actions.items():
            if call_config == CallConfig.NEVER:
                raise ValueError("???")
            existing_action = self._bare_externals.get(for_action)
            if existing_action is None:
                if override is True:
                    raise ValueError("override=True, but nothing to override")
            else:
                if override is False:
                    raise ValueError(
                        f"override=False, but bare external for {for_action} already exists."
                    )
                assert isinstance(existing_action.action, SubroutineFnWrapper)
                self.deregister_bare_method(existing_action.action)
            self._bare_externals[for_action] = OnCompleteAction(
                action=sub, call_config=call_config
            )
        self.bare_methods[python_func_name] = sub

    def deregister_bare_method(
        self,
        name_or_reference: str | SubroutineFnWrapper,
        /,
    ) -> None:
        if isinstance(name_or_reference, str):
            method = self.bare_methods.pop(name_or_reference)
        else:
            method = name_or_reference
            _remove_first_match(self.bare_methods, lambda _, v: v is method)
        _remove_first_match(self._bare_externals, lambda _, v: v.action is method)

    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
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
        bare: bool | None = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
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

        def decorator(func: HandlerFunc) -> SubroutineFnWrapper | ABIReturnSubroutine:
            python_func_name = func.__name__
            sig = inspect.signature(func)
            nonlocal bare
            if bare is None:
                bare = not sig.parameters

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

            if authorize is not None:
                func = _authorize(authorize)(func)
            if bare:
                sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)
                if sub.subroutine.argument_count():
                    raise TypeError("Bare externals must take no method arguments")

                self.register_bare_external(
                    sub,
                    python_func_name=python_func_name,
                    actions=actions,
                    override=override,
                )
                return sub
            else:
                hints = capture_method_hints_and_remove_defaults(
                    func,
                    read_only=read_only,
                    config=MethodConfig(**cast(dict[str, CallConfig], actions)),
                )
                method = ABIReturnSubroutine(func, overriding_name=name)
                setattr(method, "_read_only", read_only)

                self.register_abi_external(
                    method,
                    python_func_name=python_func_name,
                    actions=actions,
                    hints=hints,
                    override=override,
                )
                return method

        if fn is None:
            return decorator

        return decorator(fn)

    def _shortcut_external(
        self,
        *,
        action: OnCompleteActionName,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        if allow_call and allow_create:
            call_config = CallConfig.ALL
        elif allow_call:
            call_config = CallConfig.CALL
        elif allow_create:
            call_config = CallConfig.CREATE
        else:
            raise ValueError("Require one of allow_call or allow_create to be True")
        return self.external(
            method_config={action: call_config},
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )

    @overload
    def create(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def create(
        self,
        /,
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def create(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="no_op",
            allow_call=allow_call,
            allow_create=True,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def delete(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def delete(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def delete(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="delete_application",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def update(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def update(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def update(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="update_application",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def opt_in(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def opt_in(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def opt_in(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="opt_in",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def clear_state(
        self,
        fn: Callable[[], Expr],
        /,
    ) -> SubroutineFnWrapper:
        ...

    @overload
    def clear_state(
        self,
        /,
        *,
        name: str | None = None,
        override: bool | None = False,
    ) -> Callable[[Callable[[], Expr]], SubroutineFnWrapper]:
        ...

    def clear_state(
        self,
        fn: Callable[[], Expr] | None = None,
        /,
        *,
        name: str | None = None,
        override: bool | None = False,
    ) -> SubroutineFnWrapper | Callable[[Callable[[], Expr]], SubroutineFnWrapper]:
        def decorator(fun: Callable[[], Expr]) -> SubroutineFnWrapper:
            sub = SubroutineFnWrapper(fun, TealType.none, name=name)
            if override is True and self._clear_state_method is None:
                raise ValueError("override=True but no clear_state defined")
            elif override is False and self._clear_state_method is not None:
                raise ValueError("override=False but clear_state already defined")
            self._clear_state_method = sub
            return sub

        return decorator if fn is None else decorator(fn)

    @overload
    def close_out(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def close_out(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def close_out(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="close_out",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def no_op(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def no_op(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="no_op",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    def implement(
        self,
        blueprint: Callable[Concatenate["Application[TState]", P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> "Application[TState]":
        blueprint(self, *args, **kwargs)
        return self

    def build(self, client: AlgodClient | None = None) -> ApplicationSpecification:
        """Build the application specification, including transpiling the application to TEAL, and fully compiling
        any nested (i.e. precompiled) apps/lsigs to byte code.

        Note: .

        Args:
            client (optional): An Algod client that is required if there are any ``precopiled`` so they can be fully compiled.
        """

        with _set_ctx(app=self, client=client):
            bare_calls = BareCallActions(
                **cast(dict[str, OnCompleteAction], self._bare_externals)
            )
            router = Router(
                name=self.name,
                bare_calls=bare_calls,
                descr=self.descr,
                clear_state=self._clear_state_method,
            )

            # Add method externals
            hints: dict[str, MethodHints] = {}
            for abi_external in self._abi_externals.values():
                router.add_method_handler(
                    method_call=abi_external.method,
                    method_config=MethodConfig(
                        **cast(dict[str, CallConfig], abi_external.actions)
                    ),
                )
                hints[abi_external.method.name()] = abi_external.hints

            # Compile approval and clear programs
            approval_program, clear_program, contract = router.compile_program(
                version=self.compiler_options.avm_version,
                assemble_constants=self.compiler_options.assemble_constants,
                optimize=OptimizeOptions(
                    scratch_slots=self.compiler_options.scratch_slots,
                    frame_pointers=self.compiler_options.frame_pointers,
                ),
            )

        return ApplicationSpecification(
            approval_program=approval_program,
            clear_program=clear_program,
            contract=contract,
            hints=hints,
            app_state=self._app_state.dictify(),
            account_state=self._acct_state.dictify(),
            app_state_schema=self._app_state.schema,
            account_state_schema=self._acct_state.schema,
        )

    def initialize_application_state(self) -> Expr:
        """
        Initialize any application state variables declared

        :return: The Expr to initialize the application state.
        :rtype: pyteal.Expr
        """
        return self._app_state.initialize()

    def initialize_account_state(self, addr: Expr = Txn.sender()) -> Expr:
        """
        Initialize any account state variables declared

        :param addr: Optional, address of account to initialize state for.
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """

        return self._acct_state.initialize(addr)

    def dump(self, directory: str = ".", client: Optional[AlgodClient] = None) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory (optional): str path to the directory where the artifacts should be written
            client (optional): AlgodClient to be passed to any precompiles
        """
        self.build(client).dump(Path(directory))


def this_app() -> Application[TState]:
    return _ctx.get().app


@overload
def precompiled(value: Application, /) -> AppPrecompile:
    ...


@overload
def precompiled(value: "LogicSignature", /) -> LSigPrecompile:
    ...


@overload
def precompiled(value: "LogicSignatureTemplate", /) -> LSigTemplatePrecompile:
    ...


def precompiled(
    value: "Application | LogicSignature | LogicSignatureTemplate",
    /,
) -> AppPrecompile | LSigPrecompile | LSigTemplatePrecompile:
    try:
        ctx = _ctx.get()
    except LookupError:
        raise LookupError("beaker.precompiled(...) should be called inside a function")
    return ctx.app.precompiled(value)


TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


def _remove_first_match(
    m: MutableMapping[TKey, TValue], predicate: Callable[[TKey, TValue], bool]
) -> None:
    for k, v in m.items():
        if predicate(k, v):
            del m[k]
            break
