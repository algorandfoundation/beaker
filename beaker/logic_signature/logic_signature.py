from inspect import getattr_static
from pyteal import *
from beaker.decorators import get_handler_config, HandlerConfig, Method

"""
    How do we handle routing for lsigs?

    we can have up to 255 args passed which should be plenty for ABI style stuff 
    but ABI stuff requires the args be passed in Txn.application_args

    Instead of creating a Router and adding methods, create our own Router like thing and 
    force use of the first app arg to route handling to correct method?
"""


class LogicSignature:
    def __init__(self, version: int = MAX_TEAL_VERSION):
        self.teal_version = version
        self.attrs = {
            m: (getattr(self, m), getattr_static(self, m))
            for m in list(set(dir(self.__class__)) - set(dir(super())))
            if not m.startswith("__")
        }

        self.methods: dict[str, tuple[Subroutine, MethodConfig]] = {}

        for name, (bound_attr, static_attr) in self.attrs.items():
            # Check for externals and internal methods
            external_config = get_handler_config(bound_attr)
            match external_config:
                # ABI Methods
                case HandlerConfig(method_spec=Method()):
                    abi_meth = ABIReturnSubroutine(static_attr)
                    if external_config.referenced_self:
                        abi_meth.subroutine.implementation = bound_attr
                    self.methods[name] = abi_meth

                    self.hints[name] = external_config.hints()

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
