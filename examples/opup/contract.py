from typing import Literal
from pyteal import abi, ScratchVar, Seq, Assert, Int, For, Sha256
from beaker import sandbox
from beaker.decorators import external

if __name__ == "__main__":
    from op_up import OpUp
else:
    from .op_up import OpUp


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


if __name__ == "__main__":
    a, c = ExpensiveApp().compile(sandbox.get_algod_client())
    print(a, c)
