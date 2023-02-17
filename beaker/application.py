import dataclasses
import inspect
import typing
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import (
    cast,
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

from pyteal import (
    SubroutineFnWrapper,
    Txn,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
    OnCompleteAction,
    Router,
    CallConfig,
    TealType,
    MethodConfig,
    Bytes,
    Int,
    Approve,
)

from beaker.application_specification import (
    ApplicationSpecification,
    MethodHints,
    DefaultArgumentDict,
)
from beaker.build_options import BuildOptions
from beaker.decorators import authorize as authorize_decorator
from beaker.logic_signature import LogicSignature, LogicSignatureTemplate
from beaker.precompile import (
    PrecompiledApplication,
    PrecompiledLogicSignature,
    PrecompiledLogicSignatureTemplate,
)
from beaker.state._aggregate import ApplicationStateAggregate, AccountStateAggregate
from beaker.state.primitive import AccountStateValue, ApplicationStateValue

if typing.TYPE_CHECKING:
    from algosdk.v2client.algod import AlgodClient

__all__ = [
    "Application",
    "this_app",
    "precompiled",
]

OnCompleteActionName: TypeAlias = Literal[
    "no_op",
    "opt_in",
    "close_out",
    "update_application",
    "delete_application",
]

MethodConfigDict: TypeAlias = dict[OnCompleteActionName, CallConfig]

T = TypeVar("T")
P = ParamSpec("P")
TState = TypeVar("TState", covariant=True)

HandlerFunc = Callable[..., Expr]


@dataclasses.dataclass
class ABIExternal:
    actions: MethodConfigDict
    method: ABIReturnSubroutine
    hints: MethodHints


DecoratorResultType: TypeAlias = SubroutineFnWrapper | ABIReturnSubroutine
DecoratorFuncType: TypeAlias = Callable[[HandlerFunc], DecoratorResultType]


@dataclasses.dataclass(frozen=True, kw_only=True)
class BuildContext:
    app: "Application"
    client: "AlgodClient | None"


_ctx: ContextVar[BuildContext] = ContextVar("beaker.build_context")


@contextmanager
def _set_ctx(app: "Application", client: "AlgodClient | None") -> Iterator[None]:
    token = _ctx.set(BuildContext(app=app, client=client))
    try:
        yield
    finally:
        _ctx.reset(token)


class Application(Generic[TState]):
    @overload
    def __init__(
        self: "Application[None]",
        name: str,
        *,
        descr: str | None = None,
        build_options: BuildOptions | None = None,
    ):
        ...

    @overload
    def __init__(
        self: "Application[TState]",
        name: str,
        *,
        state: TState,
        descr: str | None = None,
        build_options: BuildOptions | None = None,
    ):
        ...

    def __init__(
        self,
        name: str,
        *,
        state: TState = cast(TState, None),
        descr: str | None = None,
        build_options: BuildOptions | None = None,
    ):
        """<TODO>"""
        self._state: TState = state
        self.name = name
        self.descr = descr
        self.build_options = build_options or BuildOptions()
        self.bare_methods: dict[str, SubroutineFnWrapper] = {}
        self.abi_methods: dict[str, ABIReturnSubroutine] = {}

        self._bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self._clear_state_method: SubroutineFnWrapper | None = None
        self._precompiled_lsigs: dict[LogicSignature, PrecompiledLogicSignature] = {}
        self._precompiled_lsig_templates: dict[
            LogicSignatureTemplate, PrecompiledLogicSignatureTemplate
        ] = {}
        self._precompiled_apps: dict[Application, PrecompiledApplication] = {}
        self._abi_externals: dict[str, ABIExternal] = {}
        self._acct_state = AccountStateAggregate(self._state)
        self._app_state = ApplicationStateAggregate(self._state)

    def __init_subclass__(cls) -> None:
        warnings.warn(
            "Subclassing beaker.Application is deprecated, please see the migration guide at: TODO",
            DeprecationWarning,
        )

    @property
    def state(self) -> TState:
        return self._state

    @overload
    def precompiled(self, value: "Application", /) -> PrecompiledApplication:
        ...

    @overload
    def precompiled(self, value: LogicSignature, /) -> PrecompiledLogicSignature:
        ...

    @overload
    def precompiled(
        self, value: LogicSignatureTemplate, /  # noqa: W504
    ) -> PrecompiledLogicSignatureTemplate:
        ...

    def precompiled(
        self,
        value: "Application | LogicSignature | LogicSignatureTemplate",
        /,
    ) -> PrecompiledApplication | PrecompiledLogicSignature | PrecompiledLogicSignatureTemplate:
        try:
            ctx = _ctx.get()
        except LookupError:
            raise LookupError("precompiled(...) should be called inside a function")
        if ctx.app is not self:
            raise ValueError("precompiled() used in another apps context")
        if ctx.client is None:
            raise ValueError(
                "beaker.precompiled(...) requires use of a client when calling Application.build(...)"
            )
        client = ctx.client
        match value:
            case Application() as app:
                return _lazy_setdefault(
                    self._precompiled_apps,
                    app,
                    lambda: PrecompiledApplication(app, client),
                )
            case LogicSignature() as lsig:
                return _lazy_setdefault(
                    self._precompiled_lsigs,
                    lsig,
                    lambda: PrecompiledLogicSignature(lsig, client),
                )
            case LogicSignatureTemplate() as lsig_template:
                return _lazy_setdefault(
                    self._precompiled_lsig_templates,
                    lsig_template,
                    lambda: PrecompiledLogicSignatureTemplate(lsig_template, client),
                )
            case _:
                raise TypeError("TODO write error message")

    def _register_abi_external(
        self,
        method: ABIReturnSubroutine,
        *,
        python_func_name: str,
        actions: MethodConfigDict,
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

    def _register_bare_external(
        self,
        sub: SubroutineFnWrapper,
        *,
        python_func_name: str,
        actions: MethodConfigDict,
        override: bool | None,
    ) -> None:
        if any(cc == CallConfig.NEVER for cc in actions.values()):
            raise ValueError("???")
        for for_action, call_config in actions.items():
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
        method_config: MethodConfig | MethodConfigDict | None = None,
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
        method_config: MethodConfig | MethodConfigDict | None = None,
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

            actions: MethodConfigDict
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
                func = authorize_decorator(authorize)(func)
            if bare:
                sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)
                if sub.subroutine.argument_count():
                    raise TypeError("Bare externals must take no method arguments")

                self._register_bare_external(
                    sub,
                    python_func_name=python_func_name,
                    actions=actions,
                    override=override,
                )
                return sub
            else:
                hints = _capture_method_hints_and_remove_defaults(
                    func,
                    read_only=read_only,
                    actions=actions,
                )
                method = ABIReturnSubroutine(func, overriding_name=name)
                setattr(method, "_read_only", read_only)

                self._register_abi_external(
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
        allow_call: bool,
        allow_create: bool,
        name: str | None,
        authorize: SubroutineFnWrapper | None,
        bare: bool | None,
        read_only: bool,
        override: bool | None,
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
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="no_op",
            allow_call=False,
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
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="delete_application",
            allow_call=True,
            allow_create=False,
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
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="update_application",
            allow_call=True,
            allow_create=False,
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
            if sub.subroutine.argument_count():
                raise TypeError(
                    "clear_state methods cannot fail, so cannot rely on the presence of arguments. "
                    "TODO betterify this message!!"
                )
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
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="close_out",
            allow_call=True,
            allow_create=False,
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

    def build(self, client: "AlgodClient | None" = None) -> ApplicationSpecification:
        """Build the application specification, including transpiling the application to TEAL, and fully compiling
        any nested (i.e. precompiled) apps/lsigs to byte code.

        Note: .

        Args:
            client (optional): An Algod client that is required if there are any ``precopiled`` so they can be fully compiled.
        """

        with _set_ctx(app=self, client=client):
            router = Router(
                name=self.name,
                bare_calls=self._bare_calls(),
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
                version=self.build_options.avm_version,
                assemble_constants=self.build_options.assemble_constants,
                optimize=self.build_options.optimize_options,
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

    def _bare_calls(self) -> BareCallActions:
        # turn self._bare_externals into a pyteal.BareCallActions,
        # inserting a default create method if one is not found in self._bare_externals
        # OR in self._abi_externals
        bare_calls = {str(k): v for k, v in self._bare_externals.items()}
        # check for a bare method with CallConfig.CREATE or CallConfig.ALL
        if any(oca.call_config & CallConfig.CREATE for oca in bare_calls.values()):
            pass
        # else check for an ABI method with CallConfig.CREATE or CallConfig.ALL
        elif any(
            cc & CallConfig.CREATE
            for ext in self._abi_externals.values()
            for cc in ext.actions.values()
        ):
            pass
        # else, try and insert an approval-on-create method
        else:
            if "no_op" in bare_calls:
                raise Exception(
                    f"Application {self.name} has no methods that can be invoked to create the contract, "
                    f"but does have a NoOp bare method, so one couldn't be inserted. In order to deploy the contract, "
                    f"either handle CallConfig.CREATE in the no_op bare method, or add an ABI method that handles create."
                )
            bare_calls["no_op"] = OnCompleteAction(
                action=Approve(), call_config=CallConfig.CREATE
            )
        return BareCallActions(**bare_calls)

    def initialize_application_state(self) -> Expr:
        """
        Initialize any application state variables declared

        :return: The Expr to initialize the application state.
        :rtype: pyteal.Expr
        """
        self._check_context()
        return self._app_state.initialize()

    def initialize_account_state(self, addr: Expr = Txn.sender()) -> Expr:
        """
        Initialize any account state variables declared

        :param addr: Optional, address of account to initialize state for.
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """
        self._check_context()
        return self._acct_state.initialize(addr)

    def dump(
        self, directory: str | Path | None = None, client: "AlgodClient | None" = None
    ) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory (optional): str path to the directory where the artifacts should be written
            client (optional): AlgodClient to be passed to any precompiles
        """
        if directory is None:
            output_path = Path.cwd()
        else:
            output_path = Path(directory)
        self.build(client).dump(output_path)

    def _check_context(self) -> None:
        if ctx := _ctx.get(None):
            # if inside a context (ie when an expression is being evaluated by PyTeal),
            # raise a warning when attempting to access the state (or related methods) of a different app instance
            if ctx.app is not self:
                warnings.warn(
                    f"Accessing state of Application {self.name} during compilation of Application {ctx.app.name}"
                )


def this_app() -> Application[TState]:
    return _ctx.get().app


@overload
def precompiled(value: Application, /) -> PrecompiledApplication:
    ...


@overload
def precompiled(value: LogicSignature, /) -> PrecompiledLogicSignature:
    ...


@overload
def precompiled(
    value: LogicSignatureTemplate, /  # noqa: W504
) -> PrecompiledLogicSignatureTemplate:
    ...


def precompiled(
    value: Application | LogicSignature | LogicSignatureTemplate,
    /,
) -> PrecompiledApplication | PrecompiledLogicSignature | PrecompiledLogicSignatureTemplate:
    try:
        ctx_app: Application = this_app()
    except LookupError:
        raise LookupError("beaker.precompiled(...) should be called inside a function")
    if value is ctx_app:
        raise ValueError("Attempted to precompile the current application")
    return ctx_app.precompiled(value)


TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


def _remove_first_match(
    m: MutableMapping[TKey, TValue], predicate: Callable[[TKey, TValue], bool]
) -> None:
    for k, v in m.items():
        if predicate(k, v):
            del m[k]
            break


def _lazy_setdefault(
    m: MutableMapping[TKey, TValue], key: TKey, default_factory: Callable[[], TValue]
) -> TValue:
    try:
        return m[key]
    except KeyError:
        pass
    default = default_factory()
    m[key] = default
    return default


def _capture_method_hints_and_remove_defaults(
    fn: HandlerFunc,
    read_only: bool,
    actions: dict[OnCompleteActionName, CallConfig],
) -> MethodHints:
    from pyteal.ast import abi

    sig = inspect.signature(fn)
    params = sig.parameters.copy()

    mh = MethodHints(
        read_only=read_only,
        call_config=MethodConfig(**{str(k): v for k, v in actions.items()}),
    )

    for name, param in params.items():
        match param.default:
            case Expr() | int() | str() | bytes() | ABIReturnSubroutine():
                mh.default_arguments[name] = _default_argument_from_resolver(
                    param.default
                )
                params[name] = param.replace(default=inspect.Parameter.empty)
        if inspect.isclass(param.annotation) and issubclass(
            param.annotation, abi.NamedTuple
        ):
            mh.structs[name] = {
                "name": str(param.annotation.__name__),
                "elements": [
                    [name, str(abi.algosdk_from_annotation(typ.__args__[0]))]
                    for name, typ in param.annotation.__annotations__.items()
                ],
            }

    if mh.default_arguments:
        # Fix function sig/annotations
        newsig = sig.replace(parameters=list(params.values()))
        fn.__signature__ = newsig  # type: ignore[attr-defined]

    return mh


def _default_argument_from_resolver(
    resolver: Expr | ABIReturnSubroutine | int | bytes | str,
) -> DefaultArgumentDict:

    match resolver:
        # Native types
        case int() | str() | bytes():
            return {"source": "constant", "data": resolver}
        # Expr types
        case Bytes():
            return _default_argument_from_resolver(resolver.byte_str.replace('"', ""))
        case Int():
            return _default_argument_from_resolver(resolver.value)
        case AccountStateValue() as acct_sv:
            return {
                "source": "local-state",
                "data": acct_sv.str_key(),
            }
        case ApplicationStateValue() as app_sv:
            return {
                "source": "global-state",
                "data": app_sv.str_key(),
            }
        # FunctionType
        case ABIReturnSubroutine() as fn:
            if not getattr(fn, "_read_only", None):
                raise ValueError(
                    "Only ABI methods with read_only=True should be used as default arguments to other ABI methods"
                )
            return {"source": "abi-method", "data": fn.method_spec().dictify()}
        case _:
            raise TypeError(
                f"Unexpected type for a default argument to ABI method: {type(resolver)}"
            )
