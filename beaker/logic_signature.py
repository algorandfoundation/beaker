from inspect import getattr_static

from pyteal import (
    CompileOptions,
    TealInputError,
    TealType,
    Tmpl,
    Expr,
    MAX_TEAL_VERSION,
    Seq,
    compileTeal,
    Reject,
    Mode,
    ScratchVar,
    TealBlock,
    TealSimpleBlock,
)

from beaker.utils import get_class_attributes


class TemplateVariable(Expr):
    """
    A Template Variable to be used as an attribute on LogicSignatures that
    need some hardcoded well defined behavior.

    If no ``name`` is supplied, the attribute name it was assigned to is used.

    """

    def __init__(self, stack_type: TealType, name: str | None = None):
        """initialize the TemplateVariable and the scratch var it is stored in"""
        assert stack_type in [TealType.bytes, TealType.uint64], "Must be bytes or uint"

        super().__init__()
        self.stack_type = stack_type
        self.scratch = ScratchVar(stack_type)
        self.name = name

    def __set_name__(self, owner: type, name: str) -> None:
        if self.name is None:
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

    def __init__(self, version: int = MAX_TEAL_VERSION):
        """initialize the logic signature and identify relevant attributes"""
        self.template_variables: list[TemplateVariable] = []
        for name in get_class_attributes(self.__class__, use_legacy_ordering=True):
            static_attr = getattr_static(self, name)
            if isinstance(static_attr, TemplateVariable):
                self.template_variables.append(static_attr)

        template_expressions: list[Expr] = [
            tv._init_expr() for tv in self.template_variables
        ]

        self.program = compileTeal(
            Seq(*template_expressions, self.evaluate()),
            mode=Mode.Signature,
            version=version,
            assembleConstants=True,
        )

    def evaluate(self) -> Expr:
        """
        evaluate is the main entry point to the logic of the lsig.

        Override this method to handle arbitrary logic.

        """
        return Reject()
