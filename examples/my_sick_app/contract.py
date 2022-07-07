from typing import Final

from pyteal import *
from beaker import *
from beaker.decorators import bare_handler


class MySickAppState(ApplicationState):
    counter = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )


@Subroutine(TealType.bytes)
def make_tag_key(tag: abi.String):
    return Concat(Bytes("tag:"), tag.get())


class MySickAcctState(AccountState):
    nickname = LocalStateValue(TealType.bytes, default=Bytes("j. doe"))
    tags = DynamicLocalStateValue(TealType.uint64, max_keys=10, key_gen=make_tag_key)


class MySickApp(Application):
    app_state: Final[MySickAppState] = MySickAppState()
    acct_state: Final[MySickAcctState] = MySickAcctState()

    # Overrides the default 
    @bare_handler(no_op=CallConfig.CREATE)
    def create():
        return MySickApp.app_state.initialize()

    @bare_handler(opt_in=CallConfig.CALL)
    def opt_in():
        return MySickApp.acct_state.initialize(Txn.sender())

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
