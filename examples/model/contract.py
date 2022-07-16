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
        return self.orders(order_number.encode()).set(order.encode())

    @handler
    def read_item(self, order_number: abi.Byte, *, output: Order):
        return output.decode(self.orders(order_number.encode()))
