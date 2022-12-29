from inspect import getattr_static
from typing import Optional
from algosdk.v2client.algod import AlgodClient
from pyteal import (
    CompileOptions,
    TealInputError,
    TealType,
    Tmpl,
    Expr,
    MAX_TEAL_VERSION,
    SubroutineDefinition,
    ABIReturnSubroutine,
    Seq,
    compileTeal,
    Reject,
    Mode,
    ScratchVar,
    TealBlock,
    TealSimpleBlock,
)
from beaker.decorators import get_handler_config
from beaker.precompile import AppPrecompile, LSigPrecompile


class TemplateVariable(Expr):
    """
    A Template Variable to be used as an attribute on LogicSignatures that
    need some hardcoded well defined behavior.

    If no ``name`` is supplied, the attribute name it was assigned to is used.

    """

    def __init__(self, stack_type: TealType, name: str | None = None):
        """initialize the TemplateVariable and the scratch var it is stored in"""
        assert stack_type in [TealType.bytes, TealType.uint64], "Must be bytes or uint"

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

    def __init__(self, version: int = MAX_TEAL_VERSION):
        """initialize the logic signature and identify relevant attributes"""

        self.teal_version = version
        self.program: Optional[str] = None

        # Get initial list of all attrs declared
        initial_attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in sorted(list(set(dir(self.__class__)) - set(dir(super()))))
            if not m.startswith("__")
        }

        # Make sure we preserve the ordering of declaration
        ordering = [
            m for m in list(vars(self.__class__).keys()) if not m.startswith("__")
        ]
        self.attrs = {k: initial_attrs[k] for k in ordering} | initial_attrs

        self.methods: dict[str, SubroutineDefinition] = {}

        self.template_variables: list[TemplateVariable] = []
        self.precompiles: dict[
            str, LSigPrecompile | AppPrecompile
        ] = {}  # dummy for now

        for name, (bound_attr, static_attr) in self.attrs.items():

            # Check for externals and internal methods
            handler_config = get_handler_config(bound_attr)

            if isinstance(static_attr, TemplateVariable):
                if static_attr.name is None:
                    static_attr.name = name
                self.template_variables.append(static_attr)

            elif handler_config.method_spec is not None:
                abi_meth = ABIReturnSubroutine(static_attr)
                if handler_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

                self.methods[name] = abi_meth.subroutine

            elif handler_config.subroutine is not None:
                if handler_config.referenced_self:
                    setattr(self, name, handler_config.subroutine(bound_attr))
                else:
                    setattr(
                        self.__class__,
                        name,
                        handler_config.subroutine(static_attr),
                    )

        self.compile()  # will have to be deferred if lsig contains precompiles

    def compile(self, client: Optional[AlgodClient] = None) -> str:
        if self.program is not None:
            return self.program

        template_expressions: list[Expr] = [
            tv._init_expr() for tv in self.template_variables
        ]

        self.program = compileTeal(
            Seq(*template_expressions, self.evaluate()),
            mode=Mode.Signature,
            version=self.teal_version,
            assembleConstants=True,
        )

        return self.program

    def evaluate(self) -> Expr:
        """
        evaluate is the main entry point to the logic of the lsig.

        Override this method to handle arbitrary logic.

        """
        return Reject()
