from pyteal import Expr, Int, Seq, TealType, abi

from beaker import (
    Application,
    ReservedLocalStateValue,
    unconditional_create_approval,
    unconditional_opt_in_approval,
)


# Our custom Struct
class Order(abi.NamedTuple):
    item: abi.Field[abi.String]
    quantity: abi.Field[abi.Uint16]


class StructerState:
    orders = ReservedLocalStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
        prefix="",
    )


structer_app = (
    Application("Structer", state=StructerState())
    .apply(unconditional_create_approval)
    .apply(unconditional_opt_in_approval, initialize_local_state=True)
)


@structer_app.external
def place_order(order_number: abi.Uint8, order: Order) -> Expr:
    return structer_app.state.orders[order_number].set(order.encode())


@structer_app.external(read_only=True)
def read_item(order_number: abi.Uint8, *, output: Order) -> Expr:
    return output.decode(structer_app.state.orders[order_number])


@structer_app.external
def increase_quantity(order_number: abi.Uint8, *, output: Order) -> Expr:
    return Seq(
        # Read the order from state
        (new_order := Order()).decode(structer_app.state.orders[order_number]),
        # Select out in the quantity attribute, its a TupleElement type
        # so needs to be stored somewhere
        (quant := abi.Uint16()).set(new_order.quantity),
        # Add 1 to quantity
        quant.set(quant.get() + Int(1)),
        (item := abi.String()).set(new_order.item),
        # We've gotta set all of the fields at the same time, but we can
        # borrow the item we already know about
        new_order.set(item, quant),
        # Write the new order to state
        structer_app.state.orders[order_number].set(new_order.encode()),
        # Write new order to caller
        output.decode(new_order.encode()),
    )
