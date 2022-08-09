from typing import Literal, Annotated
from pyteal import abi, ScratchVar, Seq, Assert, Int, For, Sha256
from beaker.decorators import ParameterAnnotation, external, DefaultArgument
from beaker.contracts import OpUp


class ExpensiveApp(OpUp):
    """Do expensive work to demonstrate inheriting from OpUp"""

    @external
    def hash_it(
        self,
        input: Annotated[abi.String, ParameterAnnotation(descr="The input to hash")],
        iters: Annotated[
            abi.Uint64, ParameterAnnotation(descr="The number of times to iterate")
        ],
        opup_app: Annotated[
            abi.Application,
            ParameterAnnotation(
                descr="The app id to use for opup reququests",
                default=DefaultArgument(OpUp.opup_app_id),
            ),
        ],
        *,
        output: Annotated[
            abi.StaticArray[abi.Byte, Literal[32]],
            ParameterAnnotation(
                descr="The result of hashing the input a number of times"
            ),
        ],
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
