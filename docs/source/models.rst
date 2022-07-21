Models
=======

.. module:: beaker.model

With Beaker we can define a custom structure and use it in our ABI methods.

.. autoclass:: Model

    .. automethod:: set
    .. automethod:: annotation_type

    .. automethod:: client_encode
    .. automethod:: client_decode


.. code-block:: python

    from beaker.model import Model

    class Order(Model):
        item: abi.String
        quantity: abi.Uint32

    class Modeler(Application):

        orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
            stack_type=TealType.bytes,
            max_keys=16,
        )

        
        @handler
        def place_order(self, order_number: abi.Uint8, order: Order):
            return self.orders[order_number].set(order.encode())

        @handler(read_only=True)
        def read_order(self, order_number: abi.Uint8, *, output: Order):
            return output.decode(self.orders[order_number])


The application exposes the ABI methods using the tuple encoded version of the fields specified in the model. Here it would be ``(string,uint32)``.

A method hint is available to the caller for encoding/decoding by field name. 

.. code-block:: python

    # Passing in a dict as an argument that, according to the ABI, should take a tuple 
    # The keys should match the field names
    order_number = 12
    order = {"quantity": 8, "item": "cubes"}
    app_client.call(app.place_order, order_number=order_number, order=order)

    # Call the method to read the order at the original order number and decode it
    result = app_client.call(app.read_order, order_number=order_number)
    abi_decoded = Order().client_decode(result.raw_value)

    assert order == abi_decoded
