import pyteal as pt
import pytest

from beaker import (
    GlobalStateValue,
    LocalStateValue,
    ReservedGlobalStateValue,
    ReservedLocalStateValue,
)
from beaker.state._aggregate import GlobalStateAggregate, LocalStateAggregate


def test_application_state_type() -> None:
    class BaseState:
        a = GlobalStateValue(pt.TealType.uint64)

    class MyState(BaseState):
        b = GlobalStateValue(pt.TealType.bytes)

    astate = GlobalStateAggregate(MyState)

    assert astate.schema.num_byte_slices == 1
    assert astate.schema.num_uints == 1

    class MyBigState(MyState):
        c = ReservedGlobalStateValue(pt.TealType.uint64, max_keys=64)

    with pytest.raises(Exception):
        GlobalStateAggregate(MyBigState)


def test_application_state_instance() -> None:
    class BaseState:
        a = GlobalStateValue(pt.TealType.uint64)

    class MyState(BaseState):
        def __init__(self) -> None:
            self.b = GlobalStateValue(pt.TealType.bytes, key="b")

    astate = GlobalStateAggregate(MyState())

    assert astate.schema.num_byte_slices == 1
    assert astate.schema.num_uints == 1

    class MyBigState(MyState):
        c = ReservedGlobalStateValue(pt.TealType.uint64, max_keys=64)

    with pytest.raises(Exception):
        GlobalStateAggregate(MyBigState())


def test_local_state_type() -> None:
    class BaseState:
        a = LocalStateValue(pt.TealType.uint64)

    class MyState(BaseState):
        b = LocalStateValue(pt.TealType.bytes)

    astate = LocalStateAggregate(MyState)

    assert astate.schema.num_byte_slices == 1
    assert astate.schema.num_uints == 1

    class MyBigState(MyState):
        c = ReservedLocalStateValue(pt.TealType.uint64, max_keys=16)

    with pytest.raises(Exception):
        LocalStateAggregate(MyBigState)


def test_local_state_instance() -> None:
    class BaseState:
        a = LocalStateValue(pt.TealType.uint64)

    class MyState(BaseState):
        def __init__(self) -> None:
            self.b = LocalStateValue(pt.TealType.bytes, key="b")

    astate = LocalStateAggregate(MyState())

    assert astate.schema.num_byte_slices == 1
    assert astate.schema.num_uints == 1

    class MyBigState(MyState):
        c = ReservedLocalStateValue(pt.TealType.uint64, max_keys=16)

    with pytest.raises(Exception):
        LocalStateAggregate(MyBigState())
