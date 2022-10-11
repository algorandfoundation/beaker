from typing import Final
from pyteal import (
    abi,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Seq,
    TealType,
    TxnField,
    TxnType,
)
from beaker import *


class Child(Application):
    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
    )

    @create
    def create(self):
        return Seq(
            self.initialize_application_state(),
        )

    @external
    def increment_counter(self, *, output: abi.Uint64):
        return Seq(
            self.counter.increment(),
            output.set(self.counter.get()),
        )


class Parent(Application):
    child: Precompile = Precompile(app=Child())

    @external
    def create_child(self, *, output: abi.Uint64):
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.child.approval_binary_bytes,
                    TxnField.clear_state_program: self.child.clear_binary_bytes,
                    TxnField.global_num_uints: Int(1),
                }
            ),
            output.set(InnerTxn.created_application_id()),
        )


class Grandparent(Application):
    parent: Precompile = Precompile(app=Parent())

    @external
    def create_parent(self, *, output: abi.Uint64):
        """Create a new parent app."""
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.approval_program: self.parent.approval_binary_bytes,
                    TxnField.clear_state_program: self.parent.clear_binary_bytes,
                }
            ),
            output.set(InnerTxn.created_application_id()),
        )


def demo():
    accts = sandbox.get_accounts()
    acct = accts.pop()

    # Create grandparent app and fund it
    app_client_grandparent = client.ApplicationClient(
        sandbox.get_algod_client(), Grandparent(), signer=acct.signer
    )
    grandparent_app_id, _, _ = app_client_grandparent.create()
    print(f"Created grandparent app: {grandparent_app_id}")
    app_client_grandparent.fund(1 * consts.algo)

    # Call the main app to create the sub app
    result = app_client_grandparent.call(Grandparent.create_parent)
    parent_app_id = result.return_value
    print(f"Created parent app: {parent_app_id}")

    # Create parent app client
    app_client_parent = client.ApplicationClient(
        sandbox.get_algod_client(),
        Parent(),
        signer=acct.signer,
        app_id=parent_app_id,
    )

    app_client_parent.fund(1 * consts.algo)

    # Call the parent app to create the child app
    result = app_client_parent.call(Parent.create_child)
    child_app_id = result.return_value
    print(f"Created child app: {child_app_id}")

    # Create child app client
    app_client_child = client.ApplicationClient(
        sandbox.get_algod_client(),
        Child(),
        signer=acct.signer,
        app_id=child_app_id,
    )

    app_client_child.fund(1 * consts.algo)

    # Call the child app to create the child app
    result = app_client_child.call(Child.increment_counter)
    counter_value = result.return_value
    print(f"Counter value: {counter_value}")


if __name__ == "__main__":
    demo()
