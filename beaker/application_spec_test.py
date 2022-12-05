import pyteal as pt
from beaker.application import Application
from beaker.decorators import external
from beaker.state import (
    ReservedAccountStateValue,
    ReservedApplicationStateValue,
    AccountStateValue,
    ApplicationStateValue,
)
from beaker.application_spec import ApplicationSpec


def test_app_spec():
    class CustomDataType(pt.abi.NamedTuple):
        amt: pt.abi.Field[pt.abi.Uint64]
        addr: pt.abi.Field[pt.abi.Address]

    class Specd(Application):

        res_acct_sv = ReservedAccountStateValue(pt.TealType.uint64, max_keys=2)
        res_app_sv = ReservedApplicationStateValue(pt.TealType.uint64, max_keys=2)
        acct_sv = AccountStateValue(pt.TealType.uint64)
        app_sv = ApplicationStateValue(pt.TealType.uint64)

        @external
        def empty_meth(self):
            return pt.Approve()

        @external
        def default_arg_meth(self, i: pt.abi.Uint64 = acct_sv):
            return pt.Approve()

        @external
        def custom_type_meth(self, i: CustomDataType):
            return pt.Approve()

    s = Specd()
    app_spec = ApplicationSpec(s)
    print(app_spec.dictify())
