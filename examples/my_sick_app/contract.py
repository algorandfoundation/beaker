from typing import Final

from pyteal import *
from beaker import *
from beaker.decorators import bare_handler


@Subroutine(TealType.bytes)
def make_tag_key(tag: abi.String):
    return Concat(Bytes("tag:"), tag.get())


class MySickApp(Application):

    # App state
    counter: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )

    # Account state
    nickname: Final[LocalStateValue] = LocalStateValue(
        TealType.bytes, default=Bytes("j. doe")
    )
    tags: Final[LocalStateValue] = DynamicLocalStateValue(
        TealType.uint64, max_keys=10, key_gen=make_tag_key
    )

    # Overrides the default
    @bare_handler(no_op=CallConfig.CREATE)
    def create():
        return MySickApp.initialize_app_state()

    @bare_handler(opt_in=CallConfig.CALL)
    def opt_in():
        return MySickApp.initialize_account_state(Txn.sender())

    @handler
    def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        return output.set(a.get() + b.get())

    @handler(authorize=Authorize.only(Global.creator_address()))
    def increment(*, output: abi.Uint64):
        return Seq(
            MySickApp.app_state.counter.set(MySickApp.app_state.counter + Int(1)),
            output.set(MySickApp.app_state.counter),
        )

    @handler(authorize=Authorize.only(Global.creator_address()))
    def decrement(*, output: abi.Uint64):
        return Seq(
            MySickApp.app_state.counter.set(MySickApp.app_state.counter - Int(1)),
            output.set(MySickApp.app_state.counter),
        )

    @handler
    def add_tag(tag: abi.String):
        return MySickApp.acct_state.tags(tag).set(Txn.sender(), Int(1))


if __name__ == "__main__":
    import json

    msa = MySickApp()
    print(msa.approval_program)
    print(msa.clear_program)
    print(json.dumps(msa.contract.dictify()))
