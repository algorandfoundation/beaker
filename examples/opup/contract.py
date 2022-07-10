from pyteal import *
from beaker.model import Model
from beaker.contracts import OpUp
from beaker.decorators import required_args, handler


class ExpensiveApp(OpUp):
    @handler
    def bootstrap(self, ptxn: abi.PaymentTransaction, *, output: abi.Uint64):
        return Seq(
            Assert(ptxn.get().amount() >= OpUp.min_balance),
            ExpensiveApp.create_opup(),
            output.set(ExpensiveApp.opup_app_id),
        )

    class UserRecord(Model):
        account: abi.Address
        balance: abi.Uint64
        nickname: abi.String

    @handler
    def model(self, input: UserRecord, *, output: UserRecord):
        return output.decode(input.encode())

    @handler
    @required_args(
        opup_app=OpUp.get_opup_app_id
    )  # TODO: this should come from the call to `call_opup_n`?
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

    import json

    ea = ExpensiveApp()
    for n, hints in ea.contract_hints().items():
        for k, v in hints["models"].items():
            print(f"method {n} defined model for arg {k} as {list(v)}")
    # print(ea.approval_program)
