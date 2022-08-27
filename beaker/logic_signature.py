from inspect import getattr_static
from pyteal import (
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
    Pop,
)
from beaker.decorators import get_handler_config


class TemplateVariable:
    def __init__(self, stack_type: TealType, name: str = None):
        self.stack_type = stack_type
        self.name = name

    def get_name(self) -> str:
        if self.name is None:
            raise TealInputError("Name undefined in template variable")
        return f"TMPL_{self.name.upper()}"

    def get_expr(self) -> Expr:
        name = self.get_name()

        if self.stack_type is TealType.bytes:
            return Tmpl.Bytes(name)
        else:
            return Tmpl.Int(name)


class LogicSignature:
    def __init__(self, version: int = MAX_TEAL_VERSION):

        self.teal_version = version

        self.attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.methods: dict[str, SubroutineDefinition] = {}

        self.template_values: list[TemplateVariable] = []

        for name, (bound_attr, static_attr) in self.attrs.items():

            # Check for externals and internal methods
            external_config = get_handler_config(bound_attr)

            if isinstance(static_attr, TemplateVariable):
                if static_attr.name is None:
                    static_attr.name = name
                self.template_values.append(static_attr)

            elif external_config.method_spec is not None:
                abi_meth = ABIReturnSubroutine(static_attr)
                if external_config.referenced_self:
                    abi_meth.subroutine.implementation = bound_attr

                self.methods[name] = abi_meth.subroutine

            elif external_config.subroutine is not None:
                if external_config.referenced_self:
                    setattr(self, name, external_config.subroutine(bound_attr))
                else:
                    setattr(
                        self.__class__,
                        name,
                        external_config.subroutine(static_attr),
                    )

        template_expressions: list[Expr] = [
            Pop(tv.get_expr()) for tv in self.template_values
        ]

        self.program = compileTeal(
            Seq(*template_expressions, self.evaluate()),
            mode=Mode.Signature,
            version=self.teal_version,
            assembleConstants=True,
        )

    def evaluate(self):
        return Reject()
