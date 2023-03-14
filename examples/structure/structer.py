import pyteal as pt

import beaker


# Our custom Struct
class Order(pt.abi.NamedTuple):
    item: pt.abi.Field[pt.abi.String]
    quantity: pt.abi.Field[pt.abi.Uint16]


class StructerState:
    orders = beaker.ReservedLocalStateValue(
        stack_type=pt.TealType.bytes,
        max_keys=16,
        prefix="",
    )


app = (
    beaker.Application("Structer", state=StructerState())
    # allow opt-in and initialise local/account state
    .apply(beaker.unconditional_opt_in_approval, initialize_local_state=True)
)


@app.external
def place_order(order_number: pt.abi.Uint8, order: Order) -> pt.Expr:
    return app.state.orders[order_number].set(order.encode())


@app.external(read_only=True)
def read_item(order_number: pt.abi.Uint8, *, output: Order) -> pt.Expr:
    return output.decode(app.state.orders[order_number])


@app.external
def increase_quantity(order_number: pt.abi.Uint8, *, output: Order) -> pt.Expr:
    return pt.Seq(
        # Read the order from state
        (new_order := Order()).decode(app.state.orders[order_number]),
        # Select out in the quantity attribute, its a TupleElement type
        # so needs to be stored somewhere
        (quant := pt.abi.Uint16()).set(new_order.quantity),
        # Add 1 to quantity
        quant.set(quant.get() + pt.Int(1)),
        (item := pt.abi.String()).set(new_order.item),
        # We've gotta set all of the fields at the same time, but we can
        # borrow the item we already know about
        new_order.set(item, quant),
        # Write the new order to state
        app.state.orders[order_number].set(new_order.encode()),
        # Write new order to caller
        output.decode(new_order.encode()),
    )
