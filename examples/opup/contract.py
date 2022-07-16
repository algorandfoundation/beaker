from typing import Literal
from pyteal import *
from beaker.model import Model
from beaker.contracts import OpUp
from beaker.decorators import ResolvableArguments, handler


class ExpensiveApp(OpUp):
    @handler(
        resolvable=ResolvableArguments(
            opup_app=OpUp.opup_app_id  # TODO: can we communicate this with use of `call_opup`?
        )
    )
    def hash_it(
        self,
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application,
        *,
        output: abi.StaticArray[abi.Byte, Literal[32]],
    ):

        return Seq(
            Assert(opup_app.application_id() == self.opup_app_id),
            self.call_opup(Int(255)),
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            output.decode(current.load()),
        )


if __name__ == "__main__":

    import json

    ea = ExpensiveApp()
    # print(ea.approval_program)
    # print(ea.contract.dictify())
