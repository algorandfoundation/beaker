from inspect import getattr_static
from pyteal import * 
from beaker.decorators import get_external_config

class LogicSignature:
    def __init__(self, version: int=MAX_TEAL_VERSION):
        self.teal_version = version
        self.attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.methods: dict[str, tuple[Subroutine, MethodConfig]] = {}

        for name, (bound_attr, static_attr) in self.attrs.items():
            # Check for externals and internal methods
            external_config = get_external_config(bound_attr)
            match external_config:
                # ABI Methods
                case externalConfig(method_spec=Method()):
                    # Create the ABIReturnSubroutine from the static attr
                    # but override the implementation with the bound version
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if external_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr
                    self.methods[name] = abi_meth

                    self.hints[name] = external_config.hints()

                # Internal subroutines
                case externalConfig(subroutine=Subroutine()):
                    if external_config.referenced_self:
                        setattr(self, name, external_config.subroutine(bound_attr))
                    else:
                        setattr(
                            self.__class__,
                            name,
                            external_config.subroutine(static_attr),
                        )