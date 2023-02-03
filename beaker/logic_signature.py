import inspect
from typing import Callable

from pyteal import (
    CompileOptions,
    TealType,
    Tmpl,
    Expr,
    MAX_PROGRAM_VERSION,
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

    @property
    def token(self) -> str:
        """returns the name of the template variable that should be present in the output TEAL"""
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
            tmpl = Tmpl.Bytes(self.token)
        else:
            tmpl = Tmpl.Int(self.token)
        return self.scratch.store(tmpl)


class LogicSignature:
    """
    LogicSignature allows the definition of a logic signature program.

    A LogicSignature may include constants, subroutines, and :ref:TemplateVariables as attributes

    The `evaluate` method is the entry point to the application and must be overridden in any subclass
    to call the necessary logic.
    """

    def __init__(
        self,
        expr_or_func: Callable[[], Expr] | Expr,
        *,
        avm_version: int = MAX_PROGRAM_VERSION,
    ):
        logic: Expr
        if callable(expr_or_func):
            logic = expr_or_func()
        else:
            logic = expr_or_func

        self.program = compileTeal(
            logic,
            mode=Mode.Signature,
            version=avm_version,
            assembleConstants=True,
        )


class LogicSignatureTemplate:
    """
    LogicSignature allows the definition of a logic signature program.

    A LogicSignature may include constants, subroutines, and :ref:TemplateVariables as attributes

    The `evaluate` method is the entry point to the application and must be overridden in any subclass
    to call the necessary logic.
    """

    def __init__(
        self,
        expr_or_func: Callable[..., Expr] | Expr,
        *,
        runtime_template_variables: dict[str, TealType],
        avm_version: int = MAX_PROGRAM_VERSION,
    ):
        """initialize the logic signature and identify relevant attributes"""

        self.runtime_template_variables: dict[str, RuntimeTemplateVariable] = {
            name: RuntimeTemplateVariable(stack_type=stack_type, name=name)
            for name, stack_type in runtime_template_variables.items()
        }

        logic: Expr
        if not callable(expr_or_func):
            logic = expr_or_func
        else:
            params = inspect.signature(expr_or_func).parameters
            if not (params.keys() <= runtime_template_variables.keys()):
                raise ValueError(
                    "Logic signature methods should take no arguments, unless using runtime templates"
                )
            forward_args = list(params.keys())
            logic = expr_or_func(
                *[self.runtime_template_variables[name] for name in forward_args]
            )

        self.program = compileTeal(
            Seq(
                *[tv._init_expr() for tv in self.runtime_template_variables.values()],
                logic,
            ),
            mode=Mode.Signature,
            version=avm_version,
            assembleConstants=True,
        )
