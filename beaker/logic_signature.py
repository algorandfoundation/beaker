import inspect
from collections.abc import Callable

from pyteal import (
    CompileOptions,
    Expr,
    Mode,
    ScratchVar,
    Seq,
    TealBlock,
    TealSimpleBlock,
    TealType,
    Tmpl,
    compileTeal,
)

from beaker.build_options import BuildOptions

__all__ = [
    "LogicSignature",
    "LogicSignatureTemplate",
]


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
        build_options: BuildOptions | None = None,
    ):
        logic: Expr
        if callable(expr_or_func):
            logic = expr_or_func()
        else:
            logic = expr_or_func

        self.program = _lsig_to_teal(logic, build_options=build_options)


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
        build_options: BuildOptions | None = None,
    ):
        """initialize the logic signature and identify relevant attributes"""
        if not runtime_template_variables:
            raise ValueError(
                "No runtime template variables supplied - use LogicSignature instead if that was intentional"
            )

        build_options = build_options or BuildOptions()

        self.runtime_template_variables: dict[str, RuntimeTemplateVariable] = {
            name: RuntimeTemplateVariable(stack_type=stack_type, name=name)
            for name, stack_type in runtime_template_variables.items()
        }

        logic: Expr
        if not callable(expr_or_func):
            logic = expr_or_func
        else:
            params = inspect.signature(expr_or_func).parameters
            # check that the arguments names the function takes
            # is equal to or a subset of the runtime variable names
            # - ie, the function should not take any arguments other than ones
            # we can provide (runtime template variables), but it can omit
            # some (or all) arguments if it chooses. This is useful to avoid an
            # "unused variable" warning if the purpose of the template variable
            # is just to change the logic signature address
            if not (params.keys() <= runtime_template_variables.keys()):
                invalid_args = set(params.keys()) - set(
                    runtime_template_variables.keys()
                )
                raise ValueError(
                    f"Logic signature template got unexpected arguments: {', '.join(invalid_args)}."
                )
            forward_args = list(params.keys())
            logic = expr_or_func(
                *[self.runtime_template_variables[name] for name in forward_args]
            )

        self.program = _lsig_to_teal(
            Seq(
                *[tv._init_expr() for tv in self.runtime_template_variables.values()],
                logic,
            ),
            build_options,
        )


def _lsig_to_teal(expr: Expr, build_options: BuildOptions | None) -> str:
    build_options = build_options or BuildOptions()
    return compileTeal(
        expr,
        mode=Mode.Signature,
        version=build_options.avm_version,
        assembleConstants=build_options.assemble_constants,
        optimize=build_options.optimize_options,
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
