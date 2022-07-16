from typing import Final

from pyteal import *
from beaker import *


class MySickApp(Application):

    # App state
    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )

    # Account state
    nickname: Final[AccountStateValue] = AccountStateValue(
        TealType.bytes, default=Bytes("j. doe")
    )

    @Subroutine(TealType.bytes)
    def make_tag_key(tag: abi.String):
        return Concat(Bytes("tag:"), tag.get())

    tags: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        TealType.uint64, max_keys=10, key_gen=make_tag_key
    )

    # Overrides the default
    @create
    def create(self):
        """create application"""
        return self.initialize_app_state()

    @opt_in
    def opt_in(self):
        """opt into application"""
        return self.initialize_account_state()

    @handler
    def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        """add two uint64s, produce uint64"""
        return output.set(a.get() + b.get())

    @handler(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        """increment the counter"""
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter),
        )

    @handler(authorize=Authorize.only(Global.creator_address()))
    def decrement(self, *, output: abi.Uint64):
        """decrement the counter"""
        return Seq(
            self.counter.set(self.counter - Int(1)),
            output.set(self.counter),
        )

    @handler
    def add_tag(self, tag: abi.String):
        """add a tag to a user"""
        return self.tags(tag).set(Txn.sender(), Int(1))


if __name__ == "__main__":
    import json

    msa = MySickApp()
    print(msa.approval_program)
    print(msa.clear_program)
    print(msa.app_state.schema())
    print(json.dumps(msa.contract.dictify()))
