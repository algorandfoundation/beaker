import pytest

import pyteal as pt

from .consts import Algos, MilliAlgo
from .state import ApplicationStateValue
from .annotations import (
    ResolvableArgument,
    annotated,
)
from .decorators import external, get_handler_config
from .application import Application, get_method_spec


def test_resolvable():
    from .state import (
        AccountStateValue,
        ApplicationStateValue,
        DynamicAccountStateValue,
        DynamicApplicationStateValue,
    )

    x = AccountStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = ResolvableArgument(x)
    assert r.resolve_from == "local-state"
    assert r.resolve_with == "x"

    x = DynamicAccountStateValue(pt.TealType.uint64, max_keys=1)
    r = ResolvableArgument(x[pt.Bytes("x")])
    assert r.resolve_from == "local-state"
    assert r.resolve_with == "x"

    x = ApplicationStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = ResolvableArgument(x)
    assert r.resolve_from == "global-state"
    assert r.resolve_with == "x"

    x = DynamicApplicationStateValue(pt.TealType.uint64, max_keys=1)
    r = ResolvableArgument(x[pt.Bytes("x")])
    assert r.resolve_from == "global-state"
    assert r.resolve_with == "x"

    @external(read_only=True)
    def x():
        return pt.Assert(pt.Int(1))

    r = ResolvableArgument(x)
    assert r.resolve_from == "abi-method"
    assert r.resolve_with == get_method_spec(x).dictify()

    r = ResolvableArgument(pt.Bytes("1"))
    assert r.resolve_from == "constant"
    assert r.resolve_with == "1"

    r = ResolvableArgument(pt.Int(1))
    assert r.resolve_from == "constant"
    assert r.resolve_with == 1


def test_annotations():
    class AnnotatedApp(Application):
        target_app_id = ApplicationStateValue(pt.TealType.uint64)

        default_greeting = pt.Bytes("hello")

        @external
        def default_meth_arg(
            self,
            greeting: annotated(
                pt.abi.String,
                default=default_greeting,
                descr="The greeting message to apply",
            ),
        ):
            return pt.Approve()

        @external
        def resolvable_meth_arg(
            self,
            target_app: annotated(
                pt.abi.Application,
                default=target_app_id,
                descr="The target app to make OpUp calls against",
            ),
        ):
            return pt.Approve()

        @external
        def checked_meth_arg(
            self,
            _: annotated(
                pt.abi.PaymentTransaction,
                descr="The payment to the app address for 10A to cover stuff",
                check={
                    pt.TxnField.type_enum: pt.TxnType.Payment,
                    pt.TxnField.receiver: Application.address,
                    pt.TxnField.rekey_to: pt.Global.zero_address(),
                    pt.TxnField.close_remainder_to: pt.Global.zero_address(),
                    pt.TxnField.amount: lambda amt: amt > Algos(10),
                    pt.TxnField.fee: lambda fee: fee >= MilliAlgo,
                },
            ),
        ):
            return pt.Approve()

    aa = AnnotatedApp()
