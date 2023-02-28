from pyteal import Bytes, Expr, Int, TealType, Txn, abi

from beaker import (
    Application,
    GlobalStateBlob,
    GlobalStateValue,
    LocalStateBlob,
    LocalStateValue,
    ReservedGlobalStateValue,
    ReservedLocalStateValue,
    unconditional_create_approval,
    unconditional_opt_in_approval,
)


class ExampleState:
    declared_global_value = GlobalStateValue(
        stack_type=TealType.bytes,
        default=Bytes(
            "A declared state value that is protected with the `static` flag"
        ),
        descr="A static declared variable, nothing at the protocol level protects it, "
        "only the methods defined on ApplicationState do",
        static=True,
    )

    reserved_global_value = ReservedGlobalStateValue(
        stack_type=TealType.uint64,
        max_keys=32,
        descr="A reserved app state variable, with 32 possible keys",
    )

    global_blob = GlobalStateBlob(
        keys=16,
    )

    declared_local_value = LocalStateValue(
        stack_type=TealType.uint64,
        default=Int(1),
        descr="An int stored for each account that opts in",
    )

    reserved_local_value = ReservedLocalStateValue(
        stack_type=TealType.bytes,
        max_keys=8,
        descr="A reserved state value, allowing 8 keys to be reserved, "
        "in this case byte type",
    )

    local_blob = LocalStateBlob(keys=3)


app = (
    Application("StateExample", state=ExampleState())
    .apply(unconditional_create_approval, initialize_global_state=True)
    .apply(unconditional_opt_in_approval, initialize_local_state=True)
)


@app.external
def write_local_blob(v: abi.String) -> Expr:
    return app.state.local_blob.write(Int(0), v.get())


@app.external
def read_local_blob(*, output: abi.DynamicBytes) -> Expr:
    return output.set(
        app.state.local_blob.read(Int(0), app.state.local_blob.blob.max_bytes - Int(1))
    )


@app.external
def write_global_blob(v: abi.String) -> Expr:
    return app.state.global_blob.write(Int(0), v.get())


@app.external
def read_global_blob(*, output: abi.DynamicBytes) -> Expr:
    return output.set(
        app.state.global_blob.read(
            Int(0), app.state.global_blob.blob.max_bytes - Int(1)
        )
    )


@app.external
def set_global_state_val(v: abi.String) -> Expr:
    # This will fail, since it was declared as `static` and initialized to
    # a default value during create
    return app.state.declared_global_value.set(v.get())


@app.external(read_only=True)
def get_global_state_val(*, output: abi.String) -> Expr:
    return output.set(app.state.declared_global_value)


@app.external
def set_reserved_global_state_val(k: abi.Uint8, v: abi.Uint64) -> Expr:
    # Accessing the key with square brackets, accepts both Expr and an ABI type
    # If the value is an Expr it must evaluate to `TealType.bytes`
    # If the value is an ABI type, the `encode` method is used to convert it to bytes
    return app.state.reserved_global_value[k].set(v.get())


@app.external(read_only=True)
def get_reserved_global_state_val(k: abi.Uint8, *, output: abi.Uint64) -> Expr:
    return output.set(app.state.reserved_global_value[k])


@app.external
def set_local_state_val(v: abi.Uint64) -> Expr:
    # Accessing with `[Txn.sender()]` is redundant but
    # more clear what is happening
    return app.state.declared_local_value[Txn.sender()].set(v.get())


@app.external
def incr_local_state_val(v: abi.Uint64) -> Expr:
    # Omitting [Txn.sender()] just for demo purposes
    return app.state.declared_local_value.increment(v.get())


@app.external(read_only=True)
def get_local_state_val(*, output: abi.Uint64) -> Expr:
    return output.set(app.state.declared_local_value[Txn.sender()])


@app.external
def set_reserved_local_state_val(k: abi.Uint8, v: abi.String) -> Expr:
    return app.state.reserved_local_value[k][Txn.sender()].set(v.get())


@app.external(read_only=True)
def get_reserved_local_state_val(k: abi.Uint8, *, output: abi.String) -> Expr:
    return output.set(app.state.reserved_local_value[k][Txn.sender()])


if __name__ == "__main__":
    compiled = app.build()
    print(compiled.approval_program)
