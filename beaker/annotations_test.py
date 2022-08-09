import pytest

import pyteal as pt

from .state import ApplicationStateValue
from typing import Annotated
from .decorators import (
    ParameterAnnotation,
    external,
    get_handler_config,
    ResolvableArgument,
)
from .application import Application


def test_resolvable():
    from .state import (
        AccountStateValue,
        ApplicationStateValue,
        DynamicAccountStateValue,
        DynamicApplicationStateValue,
    )

    x = AccountStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = ResolvableArgument(x)
    assert r.resolvable_class == "local-state"

    x = DynamicAccountStateValue(pt.TealType.uint64, max_keys=1)
    r = ResolvableArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "local-state"

    x = ApplicationStateValue(pt.TealType.uint64, key=pt.Bytes("x"))
    r = ResolvableArgument(x)
    assert r.resolvable_class == "global-state"

    x = DynamicApplicationStateValue(pt.TealType.uint64, max_keys=1)
    r = ResolvableArgument(x[pt.Bytes("x")])
    assert r.resolvable_class == "global-state"

    @external(read_only=True)
    def x():
        return pt.Assert(pt.Int(1))

    r = ResolvableArgument(x)
    assert r.resolvable_class == "abi-method"

    r = ResolvableArgument(pt.Bytes("1"))
    assert r.resolvable_class == "constant"

    r = ResolvableArgument(pt.Int(1))
    assert r.resolvable_class == "constant"


def test_annotations():
    class AnnotatedApp(Application):
        default_greeting = pt.Bytes("hello")

        @external
        def default_meth_arg(
            self,
            greeting: Annotated[
                pt.abi.String,
                ParameterAnnotation(
                    default=ResolvableArgument(default_greeting),
                    descr="The greeting message to apply",
                ),
            ],
            name: Annotated[
                pt.abi.String,
                ParameterAnnotation(descr="The name to use when greeting"),
            ],
            *,
            output: pt.abi.String
        ):
            return output.set(pt.Concat(greeting.get(), pt.Bytes(" "), name.get()))

    aa = AnnotatedApp()
    print(get_handler_config(aa.default_meth_arg))
