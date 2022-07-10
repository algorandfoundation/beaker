from pyteal import *
from typing import Literal
from beaker.contracts import OpUp
from beaker.decorators import bare_handler, handler


class ExpensiveApp(OpUp):
    @handler
    def bootstrap(self, ptxn: abi.PaymentTransaction, *, output: abi.Uint64):
        return Seq(
            Assert(ptxn.get().amount() >= OpUp.min_balance),
            ExpensiveApp.create_opup(),
            output.set(ExpensiveApp.opup_app_id),
        )

    @handler
    def hash_it(
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application,
        *,
        output: abi.String,
    ):
        return Seq(
            Assert(opup_app.application_id() == ExpensiveApp.opup_app_id),
            ExpensiveApp.call_opup_n(Int(255)),
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            output.set(current.load()),
        )


if __name__ == "__main__":

    ea = ExpensiveApp()
    print(ea.approval_program)
