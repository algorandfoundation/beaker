import dataclasses
import inspect
import warnings
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Concatenate,
    Generic,
    Literal,
    ParamSpec,
    TypeAlias,
    TypeVar,
    cast,
    overload,
)

from algokit_utils import (
    ApplicationSpecification,
    CallConfig,
    DefaultArgumentDict,
    MethodHints,
    OnCompleteActionName,
)
from algokit_utils import MethodConfigDict as AlgokitMethodConfigDict
from pyteal import (
    ABIReturnSubroutine,
    Approve,
    BareCallActions,
    Bytes,
    Expr,
    Int,
    MethodConfig,
    OnCompleteAction,
    Router,
    SubroutineFnWrapper,
    TealType,
    Txn,
)
from pyteal import CallConfig as PyTealCallConfig

from beaker.build_options import BuildOptions
from beaker.decorators import AuthCallable
from beaker.decorators import authorize as authorize_decorator
from beaker.logic_signature import LogicSignature, LogicSignatureTemplate
from beaker.precompile import (
    PrecompileContextError,
    PrecompiledApplication,
    PrecompiledLogicSignature,
    PrecompiledLogicSignatureTemplate,
)
from beaker.state._aggregate import GlobalStateAggregate, LocalStateAggregate

if TYPE_CHECKING:
    from algosdk.v2client.algod import AlgodClient

__all__ = [
    "Application",
    "this_app",
    "precompiled",
    "unconditional_create_approval",
    "unconditional_opt_in_approval",
]

MethodConfigDict: TypeAlias = dict[OnCompleteActionName, CallConfig | PyTealCallConfig]

T = TypeVar("T")
P = ParamSpec("P")
TState = TypeVar("TState", covariant=True)

BareHandlerFunc = Callable[[], Expr]
HandlerFunc = Callable[..., Expr]


@dataclasses.dataclass
class ABIExternal:
    actions: AlgokitMethodConfigDict
    method: ABIReturnSubroutine
    hints: MethodHints


ABIDecoratorFuncType = Callable[[HandlerFunc], ABIReturnSubroutine]
BareDecoratorFuncType = Callable[[BareHandlerFunc], SubroutineFnWrapper]

DecoratorFuncType: TypeAlias = ABIDecoratorFuncType | BareDecoratorFuncType


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
    """A class representing an Application."""

    # TODO: more

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
        state: TState = cast(TState, None),  # noqa: B008
        descr: str | None = None,
        build_options: BuildOptions | None = None,
    ):
        self._state: TState = state
        self.name = name
        self.descr = descr
        self.build_options = build_options or BuildOptions()

        self.bare_actions: dict[OnCompleteActionName, OnCompleteAction] = {}
        self.abi_externals: dict[str, ABIExternal] = {}

        self._clear_state_method: SubroutineFnWrapper | None = None
        self._precompiled_lsigs: dict[LogicSignature, PrecompiledLogicSignature] = {}
        self._precompiled_lsig_templates: dict[
            LogicSignatureTemplate, PrecompiledLogicSignatureTemplate
        ] = {}
        self._precompiled_apps: dict[Application, PrecompiledApplication] = {}
        self._local_state = LocalStateAggregate(self._state)
        self._global_state = GlobalStateAggregate(self._state)

    def __init_subclass__(cls) -> None:
        warnings.warn(
            "Subclassing beaker.Application is deprecated, please see the migration guide at: "
            "https://algorand-devrel.github.io/beaker/html/migration.html",
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
        self, value: LogicSignatureTemplate, /
    ) -> PrecompiledLogicSignatureTemplate:
        ...

    def precompiled(
        self,
        value: "Application | LogicSignature | LogicSignatureTemplate",
        /,
    ) -> PrecompiledApplication | PrecompiledLogicSignature | PrecompiledLogicSignatureTemplate:
        """Precompile an Application or LogicSignature for use in the logic of the application."""

        if value is self:
            raise PrecompileContextError("Attempted to precompile current Application")
        try:
            ctx = _ctx.get()
        except LookupError as err:
            raise PrecompileContextError(
                "precompiled must be called within a function used by an Application"
            ) from err
        if ctx.app is not self:
            raise PrecompileContextError(
                f'Application.precompiled called for app "{self.name}" inside of a function of app "{ctx.app.name}"'
            )
        if ctx.client is None:
            raise PrecompileContextError(
                "Precompilation requires use of a client when calling Application.build"
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
                raise TypeError(
                    f"Expected an Application, LogicSignature, or LogicSignatureTemplate, but got a {type(value)}"
                )

    def _register_abi_external(
        self,
        method: ABIReturnSubroutine,
        *,
        actions: AlgokitMethodConfigDict,
        hints: MethodHints,
        override: bool | None,
    ) -> None:
        assert all(cc != CallConfig.NEVER for cc in actions.values())
        method_sig = method.method_signature()
        existing_method = self.abi_externals.get(method_sig)
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
        self.abi_externals[method_sig] = ABIExternal(
            actions=actions,
            method=method,
            hints=hints,
        )

    def deregister_abi_method(
        self,
        method_signature_or_reference: str | ABIReturnSubroutine,
        /,
    ) -> None:
        if isinstance(method_signature_or_reference, str):
            sig = method_signature_or_reference
        else:
            sig = method_signature_or_reference.method_signature()
        del self.abi_externals[sig]

    def _register_bare_external(
        self,
        sub: SubroutineFnWrapper,
        *,
        actions: AlgokitMethodConfigDict,
        override: bool | None,
    ) -> None:
        assert all(cc != CallConfig.NEVER for cc in actions.values())
        for for_action, call_config in actions.items():
            existing_action = self.bare_actions.get(for_action)
            if existing_action is None:
                if override is True:
                    raise ValueError("override=True, but nothing to override")
            else:
                if override is False:
                    raise ValueError(
                        f"override=False, but bare external for {for_action} already exists"
                    )
                assert isinstance(existing_action.action, SubroutineFnWrapper)
                self.deregister_bare_method(existing_action.action)
            self.bare_actions[for_action] = OnCompleteAction(
                action=sub, call_config=PyTealCallConfig(call_config.value)
            )

    def deregister_bare_method(
        self,
        action_name_or_reference: OnCompleteActionName
        | Literal["clear_state"]
        | SubroutineFnWrapper,
        /,
    ) -> None:
        if isinstance(action_name_or_reference, SubroutineFnWrapper):
            if action_name_or_reference is self._clear_state_method:
                self._clear_state_method = None
            else:
                for k, v in self.bare_actions.items():
                    if v.action is action_name_or_reference:
                        del self.bare_actions[k]
                        break
                else:
                    raise LookupError(
                        f'Not a registered bare method: "{action_name_or_reference.name()}"'
                    )
        else:
            if action_name_or_reference == "clear_state":
                if self._clear_state_method is None:
                    # not really any reason for this, other than to match behaviour
                    # of other bare actions
                    raise KeyError("No clear_state method defined")
                self._clear_state_method = None
            else:
                del self.bare_actions[action_name_or_reference]

    # case 1: no-args
    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig | MethodConfigDict | None = None,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig | MethodConfigDict | None = None,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig | MethodConfigDict,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig | MethodConfigDict | None = None,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
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
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """
        Add the method decorated to be handled as an ABI method for the Application

        Args:
            fn: The function being wrapped.
            method_config: A MethodConfig or MethodConfigDict that defines the OnComplete fields that are valid for this method
            name: Name of ABI method. If not set, name of the python method will be used.
                Useful for method overriding.
            authorize: a subroutine with input of ``Txn.sender()`` and output uint64
                interpreted as allowed if the output>0.
            bare:
            read_only: Mark a method as callable with no fee using dryrun or simulate
            override:

        Returns:
            An ABIReturnSubroutine or SubroutineFnWrapper
        """

        if bare:
            if method_config is None:
                raise ValueError("@external(bare=True, ...) requires method_config")
            if read_only:
                raise ValueError("read_only=True has no effect on bare methods")

        actions: AlgokitMethodConfigDict
        match method_config:
            case None:
                actions = {"no_op": CallConfig.CALL}
            case MethodConfig():
                actions = {
                    cast(OnCompleteActionName, key): CallConfig(value.value)
                    for key, value in method_config.__dict__.items()
                    if value.value != CallConfig.NEVER.value
                }
            case _:
                actions = {
                    key: CallConfig(value.value)
                    for key, value in method_config.items()
                    if value.value != CallConfig.NEVER.value
                }

        if bare:

            def bare_decorator(func: BareHandlerFunc) -> SubroutineFnWrapper:
                if authorize is not None:
                    func = authorize_decorator(authorize)(func)
                sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)
                if sub.subroutine.argument_count():
                    raise TypeError("Bare methods must take no method arguments")

                self._register_bare_external(
                    sub,
                    actions=actions,
                    override=override,
                )
                return sub

            return bare_decorator

        else:

            def decorator(func: HandlerFunc) -> ABIReturnSubroutine:
                if authorize is not None:
                    func = authorize_decorator(authorize)(func)
                hints = self._capture_method_hints_and_remove_defaults(
                    func,
                    read_only=read_only,
                    actions=actions,
                )
                method = ABIReturnSubroutine(func, overriding_name=name)

                self._register_abi_external(
                    method,
                    actions=actions,
                    hints=hints,
                    override=override,
                )
                return method

            if fn is None:
                return decorator

            return decorator(fn)

    # case 1: no-args
    @overload
    def create(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def create(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def create(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def create(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def create(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def create(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application create."""
        decorator = self.external(
            method_config={"no_op": CallConfig.CREATE},
            name=name,
            authorize=authorize,
            bare=bare,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

    # case 1: no-args
    @overload
    def delete(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def delete(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def delete(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def delete(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def delete(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def delete(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application delete.

        Args:
            name: The name of the method. If not provided, the name of the method will be used.
            authorize: A function that will be called to authorize the method. If not provided, the method will not be authorized.
            bare: If True, the router will only consider the OnComplete of the app call transaction to do routing.
            override: If True, the method will override any existing method with the same name.
        """

        decorator = self.external(
            method_config={"delete_application": CallConfig.CALL},
            name=name,
            authorize=authorize,
            bare=bare,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

    # case 1: no-args
    @overload
    def update(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def update(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def update(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def update(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def update(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def update(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application update.

        Args:
            name: The name of the method. If not provided, the name of the method will be used.
            authorize: A function that will be called to authorize the method. If not provided, the method will not be authorized.
            bare: If True, the router will only consider the OnComplete of the app call transaction to do routing.
            override: If True, the method will override any existing method with the same name.
        """
        decorator = self.external(
            method_config={"update_application": CallConfig.CALL},
            name=name,
            authorize=authorize,
            bare=bare,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

    # case 1: no-args
    @overload
    def opt_in(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def opt_in(
        self,
        /,
        *,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def opt_in(
        self,
        /,
        *,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def opt_in(
        self,
        /,
        *,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def opt_in(
        self,
        /,
        *,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def opt_in(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application opt-in.

        Args:
            allow_create: If True, the method will be callable even if the application does not exist.
            name: The name of the method. If not provided, the name of the method will be used.
            authorize: A function that will be called to authorize the method. If not provided, the method will not be authorized.
            bare: If True, the router will only consider the OnComplete of the app call transaction to do routing.
            override: If True, the method will override any existing method with the same name.
        """
        decorator = self.external(
            method_config={
                "opt_in": CallConfig.ALL if allow_create else CallConfig.CALL
            },
            name=name,
            authorize=authorize,
            bare=bare,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

    # case 1: no-args
    @overload
    def close_out(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def close_out(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def close_out(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def close_out(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def close_out(
        self,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def close_out(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application close-out.

        Args:
            name: The name of the method. If not provided, the name of the method will be used.
            authorize: A function that will be called to authorize the method. If not provided, the method will not be authorized.
            bare: If True, the router will only consider the OnComplete of the app call transaction to do routing.
            override: If True, the method will override any existing method with the same name.
        """
        decorator = self.external(
            method_config={"close_out": CallConfig.CALL},
            name=name,
            authorize=authorize,
            bare=bare,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

    # case 1: no-args
    @overload
    def no_op(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    # case 2: bare arg omitted
    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 3: bare=False
    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[False],
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIDecoratorFuncType:
        ...

    # case 4: bare=True
    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: Literal[True],
        override: bool | None = False,
    ) -> BareDecoratorFuncType:
        ...

    # case 5: bare is a variable
    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool,
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
        authorize: AuthCallable | SubroutineFnWrapper | None = None,
        bare: bool = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> ABIReturnSubroutine | DecoratorFuncType:
        """Mark a method as one that should be callable during application no-op.

        Args:
            allow_call: If True, the method will be callable during application no-op after creation.
            allow_create: If True, the method will be callable during application create.
            name: The name of the method. If not provided, the name of the method will be used.
            authorize: A function that will be called to authorize the method. If not provided, the method will not be authorized.
            bare: If True, the router will only consider the OnComplete of the app call transaction to do routing.
            override: If True, the method will override any existing method with the same name.
        """

        if allow_call and allow_create:
            call_config = CallConfig.ALL
        elif allow_call:
            call_config = CallConfig.CALL
        elif allow_create:
            call_config = CallConfig.CREATE
        else:
            raise ValueError("Require one of allow_call or allow_create to be True")
        decorator = self.external(
            method_config={"no_op": call_config},
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else cast(ABIReturnSubroutine, decorator(fn))

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
        """Mark a method as one that should be callable during application clear-state.

        Args:
            name: The name of the method. If not provided, the name of the method will be used.
            override: If True, the method will override any existing method with the same name.
        """

        def decorator(fun: Callable[[], Expr]) -> SubroutineFnWrapper:
            sub = SubroutineFnWrapper(fun, TealType.none, name=name)
            if sub.subroutine.argument_count():
                raise TypeError(
                    "clear_state methods cannot fail, so cannot rely on the presence of arguments. "
                    "TODO betterify this message!!"
                )
            if override is True and self._clear_state_method is None:
                raise ValueError("override=True, but no clear_state defined")
            elif override is False and self._clear_state_method is not None:
                raise ValueError("override=False, but clear_state already defined")
            self._clear_state_method = sub
            return sub

        return decorator if fn is None else decorator(fn)

    def apply(
        self,
        func: Callable[Concatenate["Application[TState]", P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> "Application[TState]":
        """Apply a ``blueprint`` function to the application

        Args:
            func: the blueprint function to apply to the application
        """
        func(self, *args, **kwargs)
        return self

    def build(self, client: "AlgodClient | None" = None) -> ApplicationSpecification:
        """Build the application specification, including transpiling the application to TEAL, and fully compiling
        any nested (i.e. precompiled) apps/lsigs to byte code.

        Note: .

        Args:
            client (optional): An Algod client that is required if there are any ``precompiled`` so they can be fully
            compiled.
        """

        with _set_ctx(app=self, client=client):
            bare_calls = self._bare_calls()
            router = Router(
                name=self.name,
                bare_calls=bare_calls,
                descr=self.descr,
                clear_state=self._clear_state_method,
            )

            # Add method externals
            hints: dict[str, MethodHints] = {}
            for abi_external in self.abi_externals.values():
                router.add_method_handler(
                    method_call=abi_external.method,
                    method_config=MethodConfig(
                        **cast(
                            dict[str, PyTealCallConfig],
                            {
                                k: PyTealCallConfig(v.value)
                                for k, v in abi_external.actions.items()
                            },
                        )
                    ),
                )
                hints[abi_external.method.method_signature()] = abi_external.hints

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
            schema={
                "global": self._global_state.dictify(),
                "local": self._local_state.dictify(),
            },
            global_state_schema=self._global_state.schema,
            local_state_schema=self._local_state.schema,
            bare_call_config=cast(
                AlgokitMethodConfigDict,
                {
                    k: CallConfig(v.call_config.value)
                    for k, v in bare_calls.asdict().items()
                    if v.call_config.value != CallConfig.NEVER.value
                },
            ),
        )

    def _bare_calls(self) -> BareCallActions:
        # turn self._bare_externals into a pyteal.BareCallActions,
        # inserting a default create method if one is not found in self._bare_externals
        # OR in self._abi_externals
        bare_calls = {str(k): v for k, v in self.bare_actions.items()}
        # check for a bare method with CallConfig.CREATE or CallConfig.ALL
        if any(oca.call_config & CallConfig.CREATE for oca in bare_calls.values()):
            pass
        # else check for an ABI method with CallConfig.CREATE or CallConfig.ALL
        elif any(
            cc & CallConfig.CREATE
            for ext in self.abi_externals.values()
            for cc in ext.actions.values()
        ):
            pass
        # else, try and insert an approval-on-create method
        else:
            if "no_op" in bare_calls:
                raise Exception(
                    f"Application {self.name} has no methods that can be invoked to create the contract, "
                    f"but does have a NoOp bare method, so one couldn't be inserted. In order to deploy the contract, "
                    f"either handle CallConfig.CREATE in the no_op bare method, "
                    f"or add an ABI method that handles create."
                )
            bare_calls["no_op"] = OnCompleteAction(
                action=Approve(), call_config=PyTealCallConfig.CREATE
            )
        return BareCallActions(**bare_calls)

    def initialize_global_state(self) -> Expr:
        """
        Initialize any global state variables declared

        :return: The Expr to initialize the application state.
        :rtype: pyteal.Expr
        """
        self._check_context()
        return self._global_state.initialize()

    def initialize_local_state(self, addr: Expr | None = None) -> Expr:
        """
        Initialize any local state variables declared

        :param addr: Optional, address of account to initialize state for (defaults to Txn.sender()).
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """
        self._check_context()
        return self._local_state.initialize(addr or Txn.sender())

    def _check_context(self) -> None:
        if ctx := _ctx.get(None):
            # if inside a context (ie when an expression is being evaluated by PyTeal),
            # raise a warning when attempting to access the state (or related methods) of a different app instance
            if ctx.app is not self:
                warnings.warn(
                    f"Accessing state of Application {self.name} during compilation of Application {ctx.app.name}"
                )

    def _capture_method_hints_and_remove_defaults(
        self,
        fn: HandlerFunc,
        *,
        read_only: bool,
        actions: AlgokitMethodConfigDict,
    ) -> MethodHints:
        from pyteal.ast import abi

        sig = inspect.signature(fn)
        params = sig.parameters.copy()

        hints = MethodHints(
            read_only=read_only,
            call_config=cast(
                AlgokitMethodConfigDict,
                {k: CallConfig(v.value) for k, v in actions.items()},
            ),
        )

        for name, param in params.items():
            if param.default is not inspect.Parameter.empty:
                # delete the default value from the signature, for PyTeal's benefit
                params[name] = param.replace(default=inspect.Parameter.empty)

                if isinstance(param.default, ABIReturnSubroutine):
                    # we need to look up the ABIExternal to resolve
                    to_resolve = self.abi_externals[param.default.method_signature()]
                else:
                    # note that we don't need to check the type here - if it's invalid,
                    # then _default_argument_from_resolver will raise an appropriate error
                    to_resolve = param.default
                    if isinstance(to_resolve, ABIExternal):
                        if to_resolve not in self.abi_externals.values():
                            raise ValueError(
                                "Can not use another app's method as a default value"
                            )
                # add the default value resolution data to the hints
                hints.default_arguments[name] = _default_argument_from_resolver(
                    to_resolve
                )

            if inspect.isclass(param.annotation) and issubclass(
                param.annotation, abi.NamedTuple
            ):
                hints.structs[name] = {
                    "name": str(param.annotation.__name__),
                    "elements": [
                        [name, str(abi.algosdk_from_annotation(typ.__args__[0]))]
                        for name, typ in param.annotation.__annotations__.items()
                    ],
                }

        if hints.default_arguments:
            # Fix function sig/annotations
            newsig = sig.replace(parameters=list(params.values()))
            fn.__signature__ = newsig  # type: ignore[attr-defined]

        return hints


def _default_argument_from_resolver(
    resolver: Expr | ABIExternal | int | bytes | str,
) -> DefaultArgumentDict:
    from beaker.state.primitive import GlobalStateValue, LocalStateValue

    match resolver:
        # Native types
        case int() | str() | bytes():
            return {"source": "constant", "data": resolver}
        # Expr types
        case Bytes():
            return _default_argument_from_resolver(resolver.byte_str.replace('"', ""))
        case Int():
            return _default_argument_from_resolver(resolver.value)
        case LocalStateValue() as acct_sv:
            return {
                "source": "local-state",
                "data": acct_sv.str_key(),
            }
        case GlobalStateValue() as app_sv:
            return {
                "source": "global-state",
                "data": app_sv.str_key(),
            }
        # FunctionType
        case ABIExternal() as ext:
            if not ext.hints.read_only:
                raise ValueError(
                    "Only ABI methods with read_only=True should be used as default arguments to other ABI methods"
                )
            return {
                "source": "abi-method",
                "data": ext.method.method_spec().dictify(),
            }
        case _:
            raise TypeError(
                f"Unexpected type for a default argument to ABI method: {type(resolver)}"
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
def precompiled(value: LogicSignatureTemplate, /) -> PrecompiledLogicSignatureTemplate:
    ...


def precompiled(
    value: Application | LogicSignature | LogicSignatureTemplate,
    /,
) -> PrecompiledApplication | PrecompiledLogicSignature | PrecompiledLogicSignatureTemplate:
    try:
        ctx_app: Application = this_app()
    except LookupError as err:
        raise PrecompileContextError(
            "precompiled must be called within a function used by an Application"
        ) from err
    return ctx_app.precompiled(value)


def unconditional_create_approval(
    app: Application,
    *,
    initialize_global_state: bool = False,
    bare: bool = True,
) -> None:
    """"""

    @app.create(bare=bare)
    def create() -> Expr:
        if initialize_global_state:
            return app.initialize_global_state()
        return Approve()


def unconditional_opt_in_approval(
    app: Application,
    *,
    initialize_local_state: bool = False,
    bare: bool = True,
) -> None:
    @app.opt_in(bare=bare)
    def opt_in() -> Expr:
        if initialize_local_state:
            return app.initialize_local_state()
        return Approve()


TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


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
