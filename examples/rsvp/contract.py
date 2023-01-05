from pyteal import *
from beaker import (
    Application,
    ApplicationStateValue,
    AccountStateValue,
    create,
    opt_in,
    external,
    delete,
    Authorize,
)

############
# Constants#
############

# Contract address minimum balance
MIN_BAL = Int(100000)

# Algorand minimum txn fee
FEE = Int(1000)


@Subroutine(TealType.none)
def withdraw_funds():
    """Helper method that withdraws funds in the RSVP contract"""
    rsvp_bal = Balance(Global.current_application_id())
    return Seq(
        Assert(
            rsvp_bal > (MIN_BAL + FEE),
        ),
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: Txn.sender(),
                TxnField.amount: rsvp_bal - (MIN_BAL + FEE),
            }
        ),
    )


class EventRSVP(Application):
    price = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(1_000_000),
        descr="The price of the event. Default price is 1 Algo",
    )

    rsvp_count = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Number of people who RSVPed to the event",
    )

    checked_in = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="0 = not checked in, 1 = checked in",
    )

    @create
    def create(self, event_price: abi.Uint64):
        """Deploys the contract and initialze the app states"""
        return Seq(
            self.initialize_application_state(),
            self.price.set(event_price.get()),
        )

    @opt_in
    def do_rsvp(self, payment: abi.PaymentTransaction):
        """Let txn sender rsvp to the event by opting into the contract"""
        return Seq(
            Assert(
                Global.group_size() == Int(2),
                payment.get().receiver() == self.address,
                payment.get().amount() == self.price,
            ),
            self.initialize_account_state(),
            self.rsvp_count.increment(),
        )

    @external(authorize=Authorize.opted_in(Global.current_application_id()))
    def check_in(self):
        """If the Sender RSVPed, check-in the Sender"""
        return self.checked_in.set(Int(1))

    @external(authorize=Authorize.only(Global.creator_address()))
    def withdraw_external(self):
        """Let event creator to withdraw all funds in the contract"""
        return withdraw_funds()

    @delete(authorize=Authorize.only(Global.creator_address()))
    def delete(self):
        """Let event creator delete the contract. Withdraws remaining funds"""
        return If(Balance(self.address) > (MIN_BAL + FEE), withdraw_funds())

    ################
    # Read Methods #
    ################

    @external(read_only=True, authorize=Authorize.only(Global.creator_address()))
    def read_rsvp(self, *, output: abi.Uint64):
        """Read amount of RSVP to the event. Only callable by Creator."""
        return output.set(self.rsvp_count)

    @external(read_only=True)
    def read_price(self, *, output: abi.Uint64):
        """Read amount of RSVP to the event. Only callable by Creator."""
        return output.set(self.price)


rsvp = EventRSVP()


@rsvp.bare_external(close_out=CallConfig.CALL)
@rsvp.bare_external(clear_state=CallConfig.CALL)
def refund():
    """Refunds event payment to guests"""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: Txn.sender(),
                TxnField.amount: rsvp.price - FEE,
            }
        ),
        InnerTxnBuilder.Submit(),
        rsvp.rsvp_count.decrement(),
    )
