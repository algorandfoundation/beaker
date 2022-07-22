from typing import Final
from beaker import *
from pyteal import *


class StateExample(Application):

    declared_app_value: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        default=Bytes(
            "A declared state value that is protected with the `static` flag"
        ),
        descr="A static declared variable, nothing at the protocol level protects it, only the methods defined on ApplicationState do",
        static=True,
    )

    dynamic_app_value: Final[
        DynamicApplicationStateValue
    ] = DynamicApplicationStateValue(
        stack_type=TealType.uint64,
        max_keys=63,
        descr="A dynamic app state variable, with 63 possible keys",
    )

    declared_account_value: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(1),
        descr="An int stored for each account that opts in",
    )

    dynamic_account_value: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=8,
        descr="A dynamic state value, allowing 8 keys to be reserved, in this case byte type",
    )

    @create
    def create(self):
        return self.initialize_application_state()

    @opt_in
    def opt_in(self):
        return self.initialize_account_state()

    @handler
    def set_app_state_val(self, v: abi.String):
        # This will fail, since it was declared as `static` and initialized to a default value during create
        return self.declared_app_value.set(v.get())

    @handler(read_only=True)
    def get_app_state_val(self, *, output: abi.String):
        return output.set(self.declared_app_value)

    @handler
    def set_dynamic_app_state_val(self, k: abi.Uint8, v: abi.Uint64):
        # Accessing the key with square brackets, accepts both Expr and an ABI type
        # If the value is an Expr it must evaluate to `TealType.bytes`
        # If the value is an ABI type, the `encode` method is used to convert it to bytes
        return self.dynamic_app_value[k].set(v.get())

    @handler(read_only=True)
    def get_dynamic_app_state_val(self, k: abi.Uint8, *, output: abi.Uint64):
        return output.set(self.dynamic_app_value[k])

    @handler
    def set_account_state_val(self, v: abi.Uint64):
        return self.declared_account_value.set(v.get())

    @handler(read_only=True)
    def get_account_state_val(self, *, output: abi.Uint64):
        return output.set(self.declared_account_value)

    @handler
    def set_dynamic_account_state_val(self, k: abi.Uint8, v: abi.String):
        return self.dynamic_account_value[k].set(v.get())

    @handler(read_only=True)
    def get_dynamic_account_state_val(self, k: abi.Uint8, *, output: abi.String):
        return output.set(self.dynamic_account_value[k])


if __name__ == "__main__":
    se = StateExample()
    print(se.approval_program)
