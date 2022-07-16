from typing import Final
from beaker import *
from pyteal import *


class Dope(Application):

    stuff: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
    )

    @opt_in
    def opt_in(self):
        return self.initialize_account_state()

    @handler
    def doit(self, k: abi.Uint8, v: abi.String):
        return self.stuff[k].set(v.get())

    @handler(read_only=True)
    def getit(self, k: abi.Uint8, *, output: abi.String):
        return output.set(self.stuff[k])


if __name__ == "__main__":
    d = Dope()
    print(d.approval_program)
