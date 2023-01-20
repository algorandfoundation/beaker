from pyteal import *
from beaker import (
    Application,
    ApplicationStateValue,
    AccountStateValue,
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
    rsvp_bal = Balance(Global.current_application_address())
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

    rsvp = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Number of people who RSVPed to the event",
    )

    checked_in = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="0 = not checked in, 1 = checked in",
    )


rsvp = EventRSVP()


@rsvp.create
def create(event_price: abi.Uint64):
    """Deploys the contract and initialze the app states"""
    return Seq(
        rsvp.initialize_application_state(),
        rsvp.price.set(event_price.get()),
    )


@rsvp.opt_in
def do_rsvp(payment: abi.PaymentTransaction):
    """Let txn sender rsvp to the event by opting into the contract"""
    return Seq(
        Assert(
            Global.group_size() == Int(2),
            payment.get().receiver() == Global.current_application_address(),
            payment.get().amount() == rsvp.price,
        ),
        rsvp.initialize_account_state(),
        rsvp.rsvp.increment(),
    )


@rsvp.external(authorize=Authorize.opted_in(Global.current_application_id()))
def check_in():
    """If the Sender RSVPed, check-in the Sender"""
    return rsvp.checked_in.set(Int(1))


@rsvp.external(authorize=Authorize.only(Global.creator_address()))
def withdraw_external():
    """Let event creator to withdraw all funds in the contract"""
    return withdraw_funds()


@rsvp.delete(authorize=Authorize.only(Global.creator_address()))
def delete():
    """Let event creator delete the contract. Withdraws remaining funds"""
    return If(
        Balance(Global.current_application_address()) > (MIN_BAL + FEE),
        withdraw_funds(),
    )


################
# Read Methods #
################


@rsvp.external(read_only=True, authorize=Authorize.only(Global.creator_address()))
def read_rsvp(*, output: abi.Uint64):
    """Read amount of RSVP to the event. Only callable by Creator."""
    return output.set(rsvp.rsvp)


@rsvp.external(read_only=True)
def read_price(*, output: abi.Uint64):
    """Read amount of RSVP to the event. Only callable by Creator."""
    return output.set(rsvp.price)


@rsvp.external(
    method_config={"clear_state": CallConfig.CALL, "close_out": CallConfig.CALL},
    bare=True,
)
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
        rsvp.rsvp.decrement(),
    )
