from inspect import getattr_static
from pyteal import *
from beaker.decorators import get_handler_config, HandlerConfig, Method

class TemplateVariable:
    def __init__(self, stack_type: TealType, name: str = None):
        self.stack_type = stack_type
        self.name = name

    def get_expr(self)->Expr:
        name = f"TMPL_"+self.name.upper()

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

        self.methods: dict[str, Subroutine] = {}

        self.template_values: list[TemplateVariable] = []

        for name, (bound_attr, static_attr) in self.attrs.items():

            if isinstance(static_attr, TemplateVariable):
                if static_attr.name is None:
                    static_attr.name = name
                self.template_values.append(static_attr)

            # Check for externals and internal methods
            external_config = get_handler_config(bound_attr)
            match external_config:
                # ABI Methods
                case HandlerConfig(method_spec=Method()):
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if external_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr

                    self.methods[name] = abi_meth.subroutine

                # Internal subroutines
                case HandlerConfig(subroutine=Subroutine()):
                    if external_config.referenced_self:
                        setattr(self, name, external_config.subroutine(bound_attr))
                    else:
                        setattr(
                            self.__class__,
                            name,
                            external_config.subroutine(static_attr),
                        )

        template_expressions: list[Expr] = [
            Pop(tv.get_expr())
            for tv in self.template_values
        ]

        self.program = compileTeal(
            Seq(*template_expressions, self.evaluate()),
            mode=Mode.Signature,
            version=self.teal_version,
            assembleConstants=True,
        )

    def evaluate(self):
        return Reject()
