from typing import Literal
from pyteal import *
from beaker.contracts import OpUp
from beaker.decorators import ResolvableArguments, external


class ExpensiveApp(OpUp):
    """Do expensive work to demonstrate inheriting from OpUp"""

    @external(resolvable=ResolvableArguments(opup_app=OpUp.opup_app_id))
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
