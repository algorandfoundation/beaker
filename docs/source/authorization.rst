Authorization
==============

Often, Methods should only be called by certain accounts. 


Lets add a parameter to the handler to allow only the app creator to call this method.

.. code-block:: python

    from beaker import Authorize

    #...

    @handler(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter)
        )

This parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  

For more, see 

The pre-defined Authorized checks are: 

- `Authorize.only(address)` for allowing a single address access
- `Authorize.has_token(asset_id)` for whether or not the sender holds >0 of a given asset
- `Authorize.opted_in(app_id)`  for whether or not they're opted in to a given app 

But we can define our own

.. code-block:: python

    from beaker.consts import Algos

    @internal(TealType.uint64)
    def is_whale(acct: Expr):
        # Only allow accounts with 1mm algos
        return Balance(acct)>Algos(1_000_000)

    @handler(authorize=is_whale)
    def greet(*, output: abi.String):
        return output.set("hello whale")
