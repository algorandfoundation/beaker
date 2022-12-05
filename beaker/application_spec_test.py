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


# def test_app_spec():
#    class Specd(Application):
#        decl_app_val = ApplicationStateValue(pt.TealType.uint64)
#        decl_acct_val = AccountStateValue(pt.TealType.uint64)
#
#        @external(read_only=True)
#        def get_asset_id(self, *, output: pt.abi.Uint64):
#            return output.set(pt.Int(123))
#
#        @external
#        def annotated_meth(self, aid: pt.abi.Asset = get_asset_id):
#            return pt.Assert(pt.Int(1))
#
#        class Thing(pt.abi.NamedTuple):
#            a: pt.abi.Field[pt.abi.Uint64]
#            b: pt.abi.Field[pt.abi.Uint32]
#
#        @external
#        def struct_meth(self, thing: Thing):
#            return pt.Approve()
#
#    s = Specd()
#
#    actual_spec = s.application_spec()
#
#    get_asset_id_hints = {"read_only": True}
#    annotated_meth_hints = {
#        "default_arguments": {
#            "aid": {
#                "source": "abi-method",
#                "data": {
#                    "name": "get_asset_id",
#                    "args": [],
#                    "returns": {"type": "uint64"},
#                },
#            },
#        }
#    }
#    struct_meth_hints = {
#        "structs": {
#            "thing": {"name": "Thing", "elements": [("a", "uint64"), ("b", "uint32")]}
#        }
#    }
#
#    expected_hints = {
#        "get_asset_id": get_asset_id_hints,
#        "annotated_meth": annotated_meth_hints,
#        "struct_meth": struct_meth_hints,
#    }
#
#    expected_schema = {
#        "local": {
#            "declared": {
#                "decl_acct_val": {
#                    "type": "uint64",
#                    "key": "decl_acct_val",
#                    "descr": "",
#                }
#            },
#            "reserved": {},
#        },
#        "global": {
#            "declared": {
#                "decl_app_val": {
#                    "type": "uint64",
#                    "key": "decl_app_val",
#                    "descr": "",
#                }
#            },
#            "reserved": {},
#        },
#    }
#
#    def dict_match(a: dict, e: dict) -> bool:
#        for k, v in a.items():
#            if type(v) is dict:
#                if not dict_match(v, e[k]):
#                    print(f"comparing {k} {v} {e[k]}")
#                    return False
#            else:
#                if v != e[k]:
#                    print(f"comparing {k}")
#                    return False
#
#        return True
#
#    assert dict_match(actual_spec["hints"], expected_hints)
#    assert dict_match(actual_spec["schema"], expected_schema)
#


# def test_struct_args():
#    from algosdk.abi import Method, Argument, Returns
#
#    class Structed(Application):
#        class UserRecord(pt.abi.NamedTuple):
#            addr: pt.abi.Field[pt.abi.Address]
#            balance: pt.abi.Field[pt.abi.Uint64]
#            nickname: pt.abi.Field[pt.abi.String]
#
#        @external
#        def structy(self, user_record: UserRecord):
#            return pt.Assert(pt.Int(1))
#
#    m = Structed()
#
#    arg = Argument("(address,uint64,string)", name="user_record")
#    ret = Returns("void")
#    assert Method("structy", [arg], ret) == get_method_spec(m.structy)
#
#    assert m.hints["structy"].structs == {
#        "user_record": {
#            "name": "UserRecord",
#            "elements": [
#                ("addr", "address"),
#                ("balance", "uint64"),
#                ("nickname", "string"),
#            ],
#        }
#    }
