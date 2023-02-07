from typing import Final
from beaker import (
    Application,
    ApplicationStateValue,
    ReservedApplicationStateValue,
    AccountStateValue,
    ReservedAccountStateValue,
)
from pyteal import abi, TealType, Bytes, Int, Txn

from beaker.state import AccountStateBlob, ApplicationStateBlob


class ExampleState:
    account_blob: Final[AccountStateBlob] = AccountStateBlob(keys=3)

    application_blob: Final[ApplicationStateBlob] = ApplicationStateBlob(
        keys=16,
    )

    declared_account_value: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(1),
        descr="An int stored for each account that opts in",
    )

    declared_app_value: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        default=Bytes(
            "A declared state value that is protected with the `static` flag"
        ),
        descr="A static declared variable, nothing at the protocol level protects it, only the methods defined on ApplicationState do",
        static=True,
    )

    reserved_account_value: Final[
        ReservedAccountStateValue
    ] = ReservedAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=8,
        descr="A reserved state value, allowing 8 keys to be reserved, in this case byte type",
    )
    reserved_app_value: Final[
        ReservedApplicationStateValue
    ] = ReservedApplicationStateValue(
        stack_type=TealType.uint64,
        max_keys=32,
        descr="A reserved app state variable, with 32 possible keys",
    )


app = Application("StateExample", state=ExampleState)


@app.create
def create():
    return app.initialize_application_state()


@app.opt_in
def opt_in():
    return app.initialize_account_state()


@app.external
def write_acct_blob(v: abi.String):
    return app.state.account_blob.write(Int(0), v.get())


@app.external
def read_acct_blob(*, output: abi.DynamicBytes):
    return output.set(
        app.state.account_blob.read(
            Int(0), app.state.account_blob.blob.max_bytes - Int(1)
        )
    )


@app.external
def write_app_blob(v: abi.String):
    return app.state.application_blob.write(Int(0), v.get())


@app.external
def read_app_blob(*, output: abi.DynamicBytes):
    return output.set(
        app.state.application_blob.read(
            Int(0), app.state.application_blob.blob.max_bytes - Int(1)
        )
    )


@app.external
def set_app_state_val(v: abi.String):
    # This will fail, since it was declared as `static` and initialized to a default value during create
    return app.state.declared_app_value.set(v.get())


@app.external(read_only=True)
def get_app_state_val(*, output: abi.String):
    return output.set(app.state.declared_app_value)


@app.external
def set_reserved_app_state_val(k: abi.Uint8, v: abi.Uint64):
    # Accessing the key with square brackets, accepts both Expr and an ABI type
    # If the value is an Expr it must evaluate to `TealType.bytes`
    # If the value is an ABI type, the `encode` method is used to convert it to bytes
    return app.state.reserved_app_value[k].set(v.get())


@app.external(read_only=True)
def get_reserved_app_state_val(k: abi.Uint8, *, output: abi.Uint64):
    return output.set(app.state.reserved_app_value[k])


@app.external
def set_account_state_val(v: abi.Uint64):
    # Accessing with `[Txn.sender()]` is redundant but
    # more clear what is happening
    return app.state.declared_account_value[Txn.sender()].set(v.get())


@app.external
def incr_account_state_val(v: abi.Uint64):
    # Omitting [Txn.sender()] just for demo purposes
    return app.state.declared_account_value.increment(v.get())


@app.external(read_only=True)
def get_account_state_val(*, output: abi.Uint64):
    return output.set(app.state.declared_account_value[Txn.sender()])


@app.external
def set_reserved_account_state_val(k: abi.Uint8, v: abi.String):
    return app.state.reserved_account_value[k][Txn.sender()].set(v.get())


@app.external(read_only=True)
def get_reserved_account_state_val(k: abi.Uint8, *, output: abi.String):
    return output.set(app.state.reserved_account_value[k][Txn.sender()])


if __name__ == "__main__":
    compiled = app.compile()
    print(compiled.approval_program)
