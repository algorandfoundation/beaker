# example: STATE_GLOBAL
import pyteal as pt

from beaker import Application, GlobalStateValue


class CounterState:
    counter = GlobalStateValue(
        stack_type=pt.TealType.uint64,
        descr="A counter for showing how to use application state",
    )


app = Application(
    "CounterApp", descr="An app that holds a counter", state=CounterState()
)


@app.external
def increment() -> pt.Expr:
    return app.state.counter.set(app.state.counter + pt.Int(1))


@app.external
def decrement() -> pt.Expr:
    return app.state.counter.set(app.state.counter - pt.Int(1))


app_spec = app.build()
print(app_spec.global_state_schema.dictify())
# example: STATE_GLOBAL

# example: STATE_LOCAL
import pyteal as pt

from beaker import Application, LocalStateValue


class LocalCounterState:
    local_counter = LocalStateValue(
        stack_type=pt.TealType.uint64,
        descr="A counter for showing how to use application state",
    )


local_app = Application(
    "CounterApp", descr="An app that holds a counter", state=LocalCounterState()
)


@local_app.external
def user_increment() -> pt.Expr:
    return local_app.state.local_counter.set(local_app.state.local_counter + pt.Int(1))


@local_app.external
def user_decrement() -> pt.Expr:
    return local_app.state.local_counter.set(local_app.state.local_counter - pt.Int(1))


local_app_spec = local_app.build()
print(local_app_spec.local_state_schema.dictify())
# example: STATE_LOCAL

# example: STATE_MAPPING
import pyteal as pt

from beaker.lib.storage import BoxMapping


class MappingState:
    users = BoxMapping(pt.abi.Address, pt.abi.Uint64)


mapping_app = Application(
    "MappingApp", descr="An app that holds a mapping", state=MappingState()
)


@mapping_app.external
def store_user_value(value: pt.abi.Uint64) -> pt.Expr:
    # access an element in the mapping by key
    return mapping_app.state.users[pt.Txn.sender()].set(value)


# example: STATE_MAPPING


# example: STATE_LIST
import pyteal as pt

from beaker.lib.storage import BoxList


class ListState:
    users = BoxList(pt.abi.Address, 5)


list_app = Application("ListApp", descr="An app that holds a list", state=ListState())


@list_app.external
def store_user(user: pt.abi.Address, index: pt.abi.Uint64) -> pt.Expr:
    # access an element in the list by index
    return list_app.state.users[index.get()].set(user)


# example: STATE_LIST
