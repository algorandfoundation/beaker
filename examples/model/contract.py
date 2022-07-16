from typing import Final
from pyteal import *
from beaker import *
from beaker.model import *


class Modeler(Application):

    orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
    )

    class Order(Model):
        item: abi.String
        quantity: abi.Uint16

    @handler
    def place_order(self, order_number: abi.Byte, order: Order):
        return self.orders[order_number].set(order.encode())

    @handler(read_only=True)
    def read_item(self, order_number: abi.Byte, *, output: Order):
        return output.decode(self.orders[order_number])

    @handler
    def increase_quantity(self, order_number: abi.Byte, *, output: Order):
        return Seq(
            # Read the order from state
            (new_order := Modeler.Order()).decode(self.orders[order_number]),
            # Select out in the quantity attribute, its a TupleElement type
            # so needs to be stored somewhere
            (quant := abi.Uint16()).set(new_order.quantity),
            # Add 1 to quantity
            quant.set(quant.get() + Int(1)),
            # We've gotta set all of the fields at the same time, but we can
            # borrow the item we already know about
            new_order.set(new_order.item, quant),
            # Write the new order to state
            self.orders[order_number].set(new_order.encode()),
            # Write new order to caller
            output.decode(new_order.encode()),
        )
