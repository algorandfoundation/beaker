import pyteal as pt

import beaker

############
# Constants#
############

# Contract address minimum balance
MIN_BAL = pt.Int(100000)

# Algorand minimum txn fee
FEE = pt.Int(1000)


class EventRSVPState:
    price = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(1_000_000),
        descr="The price of the event. Default price is 1 Algo",
    )

    rsvp = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
        descr="Number of people who RSVPed to the event",
    )

    checked_in = beaker.LocalStateValue(
        stack_type=pt.TealType.uint64,
        default=pt.Int(0),
        descr="0 = not checked in, 1 = checked in",
    )


app = beaker.Application("EventRSVP", state=EventRSVPState())


@app.create
def create(event_price: pt.abi.Uint64) -> pt.Expr:
    """Deploys the contract and initialze the app states"""
    return pt.Seq(
        app.initialize_global_state(),
        app.state.price.set(event_price.get()),
    )


@app.opt_in
def do_rsvp(payment: pt.abi.PaymentTransaction) -> pt.Expr:
    """Let txn sender rsvp to the event by opting into the contract"""
    return pt.Seq(
        pt.Assert(
            pt.Global.group_size() == pt.Int(2),
            payment.get().receiver() == pt.Global.current_application_address(),
            payment.get().amount() == app.state.price,
        ),
        app.initialize_local_state(),
        app.state.rsvp.increment(),
    )


@app.external(authorize=beaker.Authorize.opted_in())
def check_in() -> pt.Expr:
    """If the Sender RSVPed, check-in the Sender"""
    return app.state.checked_in.set(pt.Int(1))


@app.external(authorize=beaker.Authorize.only_creator())
def withdraw_external() -> pt.Expr:
    """Let event creator to withdraw all funds in the contract"""
    return withdraw_funds()


@app.delete(bare=True, authorize=beaker.Authorize.only_creator())
def delete() -> pt.Expr:
    """Let event creator delete the contract. Withdraws remaining funds"""
    return pt.If(
        pt.Balance(pt.Global.current_application_address()) > (MIN_BAL + FEE),
        withdraw_funds(),
    )


@pt.Subroutine(pt.TealType.none)
def withdraw_funds() -> pt.Expr:
    """Helper method that withdraws funds in the RSVP contract"""
    rsvp_bal = pt.Balance(pt.Global.current_application_address())
    return pt.Seq(
        pt.Assert(
            rsvp_bal > (MIN_BAL + FEE),
        ),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.Payment,
                pt.TxnField.receiver: pt.Txn.sender(),
                pt.TxnField.amount: rsvp_bal - (MIN_BAL + FEE),
            }
        ),
    )


################
# Read Methods #
################


@app.external(read_only=True, authorize=beaker.Authorize.only_creator())
def read_rsvp(*, output: pt.abi.Uint64) -> pt.Expr:
    """Read amount of RSVP to the event. Only callable by Creator."""
    return output.set(app.state.rsvp)


@app.external(read_only=True)
def read_price(*, output: pt.abi.Uint64) -> pt.Expr:
    """Read amount of RSVP to the event."""
    return output.set(app.state.price)


@app.close_out(bare=True)
def refund() -> pt.Expr:
    return _do_refund()


@app.clear_state
def clear_state() -> pt.Expr:
    return _do_refund()


def _do_refund() -> pt.Expr:
    """Refunds event payment to guests"""
    return pt.Seq(
        pt.InnerTxnBuilder.Begin(),
        pt.InnerTxnBuilder.SetFields(
            {
                pt.TxnField.type_enum: pt.TxnType.Payment,
                pt.TxnField.receiver: pt.Txn.sender(),
                pt.TxnField.amount: app.state.price - FEE,
            }
        ),
        pt.InnerTxnBuilder.Submit(),
        app.state.rsvp.decrement(),
    )
