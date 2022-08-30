from typing import Literal
from pyteal import abi, ScratchVar, Seq, Assert, Int, For, Sha256
from beaker.decorators import external
from beaker.contracts import OpUp


class ExpensiveApp(OpUp):
    """Do expensive work to demonstrate inheriting from OpUp"""

    @external
    def hash_it(
        self,
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application = OpUp.opup_app_id,
        *,
        output: abi.StaticBytes[Literal[32]],
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
