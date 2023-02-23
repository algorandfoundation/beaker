from pyteal import (
    Assert,
    Balance,
    Expr,
    Global,
    If,
    InnerTxnBuilder,
    Int,
    Seq,
    Subroutine,
    TealType,
    Txn,
    TxnField,
    TxnType,
    abi,
)

from beaker import (
    Application,
    Authorize,
    GlobalStateValue,
    LocalStateValue,
)

############
# Constants#
############

# Contract address minimum balance
MIN_BAL = Int(100000)

# Algorand minimum txn fee
FEE = Int(1000)


@Subroutine(TealType.none)
def withdraw_funds() -> Expr:
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


class EventRSVPState:
    price = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(1_000_000),
        descr="The price of the event. Default price is 1 Algo",
    )

    rsvp = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Number of people who RSVPed to the event",
    )

    checked_in = LocalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="0 = not checked in, 1 = checked in",
    )


rsvp = Application("EventRSVP", state=EventRSVPState())


@rsvp.create
def create(event_price: abi.Uint64) -> Expr:
    """Deploys the contract and initialze the app states"""
    return Seq(
        rsvp.initialize_global_state(),
        rsvp.state.price.set(event_price.get()),
    )


@rsvp.opt_in
def do_rsvp(payment: abi.PaymentTransaction) -> Expr:
    """Let txn sender rsvp to the event by opting into the contract"""
    return Seq(
        Assert(
            Global.group_size() == Int(2),
            payment.get().receiver() == Global.current_application_address(),
            payment.get().amount() == rsvp.state.price,
        ),
        rsvp.initialize_local_state(),
        rsvp.state.rsvp.increment(),
    )


@rsvp.external(authorize=Authorize.opted_in(Global.current_application_id()))
def check_in() -> Expr:
    """If the Sender RSVPed, check-in the Sender"""
    return rsvp.state.checked_in.set(Int(1))


@rsvp.external(authorize=Authorize.only(Global.creator_address()))
def withdraw_external() -> Expr:
    """Let event creator to withdraw all funds in the contract"""
    return withdraw_funds()


@rsvp.delete(authorize=Authorize.only(Global.creator_address()))
def delete() -> Expr:
    """Let event creator delete the contract. Withdraws remaining funds"""
    return If(
        Balance(Global.current_application_address()) > (MIN_BAL + FEE),
        withdraw_funds(),
    )


################
# Read Methods #
################


@rsvp.external(read_only=True, authorize=Authorize.only(Global.creator_address()))
def read_rsvp(*, output: abi.Uint64) -> Expr:
    """Read amount of RSVP to the event. Only callable by Creator."""
    return output.set(rsvp.state.rsvp)


@rsvp.external(read_only=True)
def read_price(*, output: abi.Uint64) -> Expr:
    """Read amount of RSVP to the event. Only callable by Creator."""
    return output.set(rsvp.state.price)


def _do_refund() -> Expr:
    """Refunds event payment to guests"""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: Txn.sender(),
                TxnField.amount: rsvp.state.price - FEE,
            }
        ),
        InnerTxnBuilder.Submit(),
        rsvp.state.rsvp.decrement(),
    )


@rsvp.close_out(name="refund")
def close_out() -> Expr:
    return _do_refund()


@rsvp.clear_state(name="refund")
def clear_state() -> Expr:
    return _do_refund()
