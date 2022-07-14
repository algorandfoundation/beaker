from typing import Final
from beaker import *
from pyteal import *


class Dope(Application):

    stuff: Final[DynamicLocalStateValue] = DynamicLocalStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
        key_gen=Subroutine(TealType.bytes)(lambda i: Suffix(Itob(i), Int(7))),
    )

    @Bare.opt_in
    def optin(self):
        return self.initialize_account_state(Txn.sender())

    @handler
    def doit(self, k: abi.Uint64, v: abi.String):
        return self.stuff(k.get()).set(Txn.sender(), v.get())

    @handler(read_only=True)
    def getit(self, k: abi.Uint64, *, output: abi.String):
        return output.set(self.stuff(k.get()).get(Txn.sender()))


if __name__ == "__main__":
    d = Dope()
    print(d.approval_program)
