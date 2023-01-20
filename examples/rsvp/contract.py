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


#
# # ^^ untouchable
# # rsvp.on_complete_actions = []
# #
# # to_remove = rsvp.on_complete_actions[0]
# # rsvp.remove_on_complete(to_remove)
# def foobar(app: Application) -> Expr:
#     return Int(1)
#
#
# class Arc420App(Application):
#     @external
#     def foobar(self) -> Expr:
#         return foobar(None)
#
#     @external(name="foobar")
#     def blah(self, i: Expr) -> Expr:
#         return i
#
#
# class MyApp(Arc420App):
#     @delete
#     def foobar(self) -> Expr:
#         return super().foobar() + Int(2)
#
#     @exernal(name="foobar")
#     def foasdfasdf(self) -> Expr:
#         return Bytes(b"")
#
#
#
#
def implements_arc420(app: Application, num: int) -> Application:
    @app.external()
    def foobar() -> Expr:
        return Int(num)

    @app.external(name="foobar")
    def foobar2(i: Expr) -> Expr:
        return i + Int(num)

    return app


#
my_arc420 = Application()
my_arc420.implement(implements_arc420, num=2)

my_arc420.methods.foobar
#
# # @rsvp.external(
# #     bare=True, override=True, method_config={"delete_application": CallConfig.CALL}
# # )
# # @rsvp.delete(override=True)
# my_arc420.
# @my_arc420.methods.foobar(abi.Uint64, abi.Uint64, returns=abi.U).override()
# #@my_arc420.methods["foobar(uint64)uint64"].override
# @my_arc420.external(name="foobar")
# def something_new(i: abi.Uint64):
#     x = foobar(rsvp)
#     pass
#
#
# # Needs:
# # .) overloading (additional signature, same name)
# # .) replacing (new signature)
# # .) overriding (existing signature)
# # .) for bare methods, overriding by OnCompleteAction
# # .) reference to closures
# # .) call original implementation (maybe just export the method?)
