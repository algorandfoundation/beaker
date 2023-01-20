import base64
import dataclasses
import inspect
import itertools
import json
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
    Iterable,
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
    MethodHints,
    MethodConfig,
    HandlerFunc,
    _authorize,
    _capture_structs_and_defaults,
    HandlerConfig,
)
from beaker.errors import BareOverwriteError
from beaker.logic_signature import LogicSignature
from beaker.precompile import AppPrecompile, LSigPrecompile
from beaker.state import AccountState, ApplicationState


def get_method_spec(fn: Any) -> Method:
    if isinstance(fn, ABIReturnSubroutine):
        return fn.method_spec()

    raise Exception("Expected argument to be an ABI method")


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


DecoratorResultType: TypeAlias = SubroutineFnWrapper | ABIReturnSubroutine
DecoratorFuncType: TypeAlias = Callable[[HandlerFunc], DecoratorResultType]


class Methods:
    __slots__ = ("_methods",)

    def __init__(self, methods: dict[str, Method] | None = None):
        self._methods: dict[str, Method] = methods or {}

    def __getattr__(self, item: str) -> Method:
        try:
            return self._methods[item]
        except KeyError as ex:
            raise AttributeError(f"Unknown method: {item}") from ex


class Application:
    def __init__(
        self,
        *,
        version: int = MAX_TEAL_VERSION,
        # TODO
        # name: str,
        # default_approve_create: bool = True, # what to name this? how does it work? why am I here?
        # descr: str | None,
        # state: TState # how to make this generic but also default to empty?!?!!?
    ) -> None:
        """<TODO>"""
        self.teal_version = version
        self._compiled: CompiledApplication | None = None
        self._bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self._lsig_precompiles: dict[LogicSignature, LSigPrecompile] = {}
        self._app_precompiles: dict[Application, AppPrecompile] = {}
        self._abi_externals: dict[str, ABIExternal] = {}
        self.acct_state = AccountState(klass=self.__class__)
        self.app_state = ApplicationState(klass=self.__class__)
        self.methods = Methods()

        # if default_approve_create:
        #
        #     @self.create
        #     def create():
        #         return Approve()

    # def unconditional_create_approval(self: Self) -> Self:
    #     self.create(lambda: Approve(), name="create", bare=True)
    #     return self

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
        return list(itertools.chain(self.app_precompiles, self.lsig_precompiles))

    @property
    def app_precompiles(self) -> Iterable[AppPrecompile]:
        return self._app_precompiles.values()

    @property
    def lsig_precompiles(self) -> Iterable[LSigPrecompile]:
        return self._lsig_precompiles.values()

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
        # TODO: this replaces references when trying to overload
        self.methods._methods[method.name()] = method.method_spec()
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
        bare: bool | None = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType:
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
                for for_action, call_config in actions.items():
                    self.register_bare_external(
                        sub,
                        for_action=for_action,
                        call_config=call_config,
                        override=override,
                    )
                return sub
            else:
                if authorize is not None:
                    func = _authorize(authorize)(func)
                method = ABIReturnSubroutine(func, overriding_name=name)
                method._read_only = read_only  # type: ignore[attr-defined]
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
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType:
        ...

    @overload
    def create(
        self,
        fn: None = None,
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
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
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
        override: bool | None = None,
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
        override: bool | None = None,
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
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
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
        override: bool | None = None,
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
        override: bool | None = None,
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
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
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
        override: bool | None = None,
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
        override: bool | None = None,
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
        fn: HandlerFunc,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
    ) -> DecoratorResultType:
        ...

    @overload
    def clear_state(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
    ) -> DecoratorFuncType:
        ...

    def clear_state(
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
        override: bool | None = None,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="clear_state",
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
    def close_out(
        self,
        fn: HandlerFunc,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
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
        override: bool | None = None,
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
        override: bool | None = None,
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
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = None,
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
        override: bool | None = None,
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
        override: bool | None = None,
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

    @property
    def on_create(self) -> Method | None:
        return self._compiled and self._compiled.on_create

    @property
    def on_update(self) -> Method | None:
        return self._compiled and self._compiled.on_update

    @property
    def on_opt_in(self) -> Method | None:
        return self._compiled and self._compiled.on_opt_in

    @property
    def on_close_out(self) -> Method | None:
        return self._compiled and self._compiled.on_close_out

    @property
    def on_clear_state(self) -> Method | None:
        return self._compiled and self._compiled.on_clear_state

    @property
    def on_delete(self) -> Method | None:
        return self._compiled and self._compiled.on_delete

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

        if self._compiled is None:

            # make sure all the precompiles are available
            for precompile in self.precompiles:
                precompile.compile(client)

            bare_call_kwargs = {str(k): v for k, v in self._bare_externals.items()}
            # if self.auto_default_create:
            #     any_create = any(
            #         x.call_config & CallConfig.CREATE for x in bare_call_kwargs.values()
            #     ) or any(
            #         cc & CallConfig.CREATE
            #         for abi in self._abi_externals.values()
            #         for cc in abi.actions.values()
            #     )
            #     if not any_create:
            #         if "no_op" in bare_call_kwargs:
            #             raise ValueError(
            #                 "default create not implemented, already a bare no_op method"
            #             )
            #         bare_call_kwargs["no_op"] = OnCompleteAction(
            #             action=SubroutineFnWrapper(
            #                 lambda: Approve(), return_type=TealType.none, name="create"
            #             ),
            #             call_config=CallConfig.CREATE,
            #         )
            router = Router(
                name=self.__class__.__name__,
                bare_calls=BareCallActions(**bare_call_kwargs),
                descr=self.__doc__,
            )

            # Add method externals
            all_creates = []
            all_updates = []
            all_deletes = []
            all_opt_ins = []
            all_close_outs = []
            all_clear_states = []
            for abi_external in self._abi_externals.values():
                method_config = MethodConfig(
                    **{str(a): cc for a, cc in abi_external.actions.items()}
                )
                router.add_method_handler(
                    method_call=abi_external.method,
                    method_config=method_config,
                )
                if any(
                    cc1 == CallConfig.CREATE or cc1 == CallConfig.ALL
                    for cc1 in dataclasses.astuple(method_config)
                ):
                    all_creates.append(abi_external.method)
                if method_config.update_application != CallConfig.NEVER:
                    all_updates.append(abi_external.method)
                if method_config.delete_application != CallConfig.NEVER:
                    all_deletes.append(abi_external.method)
                if method_config.opt_in != CallConfig.NEVER:
                    all_opt_ins.append(abi_external.method)
                if method_config.clear_state != CallConfig.NEVER:
                    all_clear_states.append(abi_external.method)
                if method_config.close_out != CallConfig.NEVER:
                    all_close_outs.append(abi_external.method)

            kwargs: dict[str, Method | None] = {
                "on_create": all_creates.pop() if len(all_creates) == 1 else None,
                "on_update": all_updates.pop() if len(all_updates) == 1 else None,
                "on_delete": all_deletes.pop() if len(all_deletes) == 1 else None,
                "on_opt_in": all_opt_ins.pop() if len(all_opt_ins) == 1 else None,
                "on_close_out": all_close_outs.pop()
                if len(all_close_outs) == 1
                else None,
                "on_clear_state": (
                    all_clear_states.pop() if len(all_clear_states) == 1 else None,
                ),
            }
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
                **kwargs,
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

    on_create: Method | None = dataclasses.field(default=None, kw_only=True)
    on_update: Method | None = None
    on_opt_in: Method | None = None
    on_close_out: Method | None = None
    on_clear_state: Method | None = None
    on_delete: Method | None = None

    def dump(self, directory: Path) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory: path to the directory where the artifacts should be written
        """
        directory.mkdir(exist_ok=True, parents=True)

        (directory / "approval.teal").write_text(self.approval_program)
        (directory / "clear.teal").write_text(self.clear_program)
        (directory / "contract.json").write_text(
            json.dumps(self.contract.dictify(), indent=4)
        )
        (directory / "application.json").write_text(
            json.dumps(self.application_spec, indent=4)
        )
