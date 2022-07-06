from typing import Final

from pyteal import *
from beaker import *


class MySickAppState(ApplicationState):
    counter = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )


class MySickAcctState(AccountState):
    nickname = LocalStateValue(TealType.bytes, default=Bytes("j. doe"))
    tags = DynamicLocalStateValue(
        TealType.uint64,
        max_keys=10,
        key_gen=Subroutine(TealType.bytes, name="make_key")(
            lambda v: Concat(Bytes("tag:"), v)
        ),
    )


class MySickApp(Application):
    app_state: Final[MySickAppState] = MySickAppState()
    acct_state: Final[MySickAcctState] = MySickAcctState()

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
        return MySickApp.acct_state.tags(tag.get()).set(Txn.sender(), Int(1))


if __name__ == "__main__":
    import json

    msa = MySickApp()
    print(msa.approval_program)
    print(msa.clear_program)
    print(json.dumps(msa.contract.dictify()))
