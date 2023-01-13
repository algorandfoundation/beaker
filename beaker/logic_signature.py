import inspect
from typing import Callable

from pyteal import (
    CompileOptions,
    TealInputError,
    TealType,
    Tmpl,
    Expr,
    MAX_TEAL_VERSION,
    Seq,
    compileTeal,
    Mode,
    ScratchVar,
    TealBlock,
    TealSimpleBlock,
)


class RuntimeTemplateVariable(Expr):
    """
    A Template Variable to be used as an attribute on LogicSignatures that
    need some hardcoded well defined behavior.

    If no ``name`` is supplied, the attribute name it was assigned to is used.

    """

    def __init__(self, stack_type: TealType, name: str):
        """initialize the TemplateVariable and the scratch var it is stored in"""
        assert stack_type in [TealType.bytes, TealType.uint64], "Must be bytes or uint"

        super().__init__()

        self.stack_type = stack_type
        self.scratch = ScratchVar(stack_type)
        self.name = name

    def get_name(self) -> str:
        """returns the name of the template variable that should be present in the output TEAL"""
        assert self.name is not None, TealInputError(
            "Name undefined in template variable"
        )
        return f"TMPL_{self.name.upper()}"

    def __str__(self) -> str:
        return f"(TemplateVariable {self.name})"

    def __teal__(self, options: CompileOptions) -> tuple[TealBlock, TealSimpleBlock]:
        return self.scratch.load().__teal__(options)

    def has_return(self) -> bool:
        """"""
        return False

    def type_of(self) -> TealType:
        """"""
        return self.stack_type

    def _init_expr(self) -> Expr:
        if self.stack_type is TealType.bytes:
            return self.scratch.store(Tmpl.Bytes(self.get_name()))
        return self.scratch.store(Tmpl.Int(self.get_name()))


class LogicSignature:
    """
    LogicSignature allows the definition of a logic signature program.

    A LogicSignature may include constants, subroutines, and :ref:TemplateVariables as attributes

    The `evaluate` method is the entry point to the application and must be overridden in any subclass
    to call the necessary logic.
    """

    def __init__(
        self,
        evaluate: Callable[..., Expr] | Expr,
        *,
        runtime_template_variables: dict[str, TealType] | None = None,
        teal_version: int = MAX_TEAL_VERSION,
    ):
        """initialize the logic signature and identify relevant attributes"""
        self._runtime_template_variables = runtime_template_variables or {}

        forward_args: list[str]
        if not callable(evaluate):
            forward_args = []
        else:
            params = inspect.signature(evaluate).parameters
            if not (params.keys() <= self._runtime_template_variables.keys()):
                raise ValueError(
                    "Logic signature methods should take no arguments, unless using runtime templates"
                )
            forward_args = list(params.keys())

        self._rtt_vars = {
            name: RuntimeTemplateVariable(stack_type=stack_type, name=name)
            for name, stack_type in self._runtime_template_variables.items()
        }

        def func(*args: Expr) -> Expr:
            if not callable(evaluate):
                return evaluate
            else:
                return evaluate(*args)

        if not self._rtt_vars:
            logic = func()
        else:
            logic = Seq(
                *[tv._init_expr() for tv in self._rtt_vars.values()],
                func(*[self._rtt_vars[name] for name in forward_args]),
            )
        self.program = compileTeal(
            logic,
            mode=Mode.Signature,
            version=teal_version,
            assembleConstants=True,
        )

    @property
    def template_variables(self) -> list[RuntimeTemplateVariable]:
        return list(self._rtt_vars.values())

    def compile(self) -> str:
        return self.program
