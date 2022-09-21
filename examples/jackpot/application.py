from pyteal import *
from beaker import *


class Jackpot(Application):

    deposit_amount: AccountStateValue = AccountStateValue(TealType.uint64)

    @opt_in
    def opt_in(self, deposit: abi.PaymentTransaction):
        return Seq(
            Assert(
                deposit.get().amount() == consts.Algos(5), comment="must be 5 algos"
            ),
            Assert(deposit.get().receiver() == self.address, comment="must be to me"),
            self.deposit_amount[Txn.sender()].set(deposit.get().amount()),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def payout(self, winner: abi.Account):
        return Seq(
            Assert(self.deposit_amount[winner.address()] == consts.Algos(5)),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.receiver: winner.address(),
                    TxnField.amount: Int(0),
                    TxnField.close_remainder_to: winner.address(),
                }
            ),
        )


if __name__ == "__main__":
    Jackpot().dump()
