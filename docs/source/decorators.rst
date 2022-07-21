Decorators
===========

.. module:: beaker

handler
----------

 TODO - Examples of calling the handler with all the options set

.. autofunction:: handler



.. _authorization:

Authorization
^^^^^^^^^^^^^

Often, we would like to restrict the accounts that may call certain methods. 

.. autoclass:: Authorize


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



.. _method_hints:

Method Hints
^^^^^^^^^^^^

A Method may provide hints to the caller to help provide context for the call. Currently Method hints are one of:

- :ref:`Resolvable <resolvable>` - A hint for the caller to "resolve" some required argument.
- :doc:`models` - A list of model field names associated to some abi Tuple. 
- :ref:`Read Only <read_only>` - A boolean flag indicating how this method should be called. 


.. _resolvable:

Resolvable (*Experimental*)


In an above example, there is a required argument `opup_app`, the id of the application that we use to increase our budget via inner app calls. This value should not change frequently, if at all, but is still required to be passed so we may _use_ it in our logic. We can provide a caller the information to `resolve` the appropriate app id using the `resolvable` keyword argument of the handler. 

We can change the handler to provide the hint.

.. code-block:: python

    @handler(
        resolvable=ResolvableArguments(
            opup_app=OpUp.opup_app_id 
        )
    )

With this handler config argument, we communicate to a caller the application expects be passed a value that can bee resolved by retrieving the state value in the application state for `opup_app_id`.  This allows the `ApplicationClient` to figure out what the appropriate application id _should_ be if necessary. 

Options for resolving arguments are:

- A constant, `str | int`
- State Values, `ApplicationStateValue | AccountStateValue (only for sender)`
- A read-only ABI method  (If we need access to a Dynamic state value, use an ABI method to produce the expected value)


Here we call the method, omitting the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the `ApplicationClient` checks to see that all the expected arguments are passed, if not it will check for hints to see if one is specified for the missing argument and try to resolve it by calling the method and setting the value of the argument to the return value of the hint.


.. _read_only:

Read Only
^^^^^^^^^

Methods that are meant to only produce information, having no side effects, should be flagged as read only. 

See `ARC22 <https://github.com/algorandfoundation/ARCs/pull/79>`_ for more details.

.. code-block:: python

    count = ApplicationStateValue(stack_type=TealType.uint64) 

    @handler(read_only=True)
    def get_count(self, id_of_thing: abi.Uint8, *, output: abi.Uint64):
        return output.set(self.count)



.. _bare_handlers:

Bare Handlers
--------------

The ARC4 spec allows applications to define handlers for ``bare`` methods, that is methods with no application arguments. 

Routing for ``bare`` methods is based on the transaction's ``OnComplete`` and whether or not it's a Create transaction.

Single Bare Handlers
^^^^^^^^^^^^^^^^^^^^

If a single OnComplete should be handled by a given method, use one of the pre-defined helpers.

.. autofunction:: create
.. autofunction:: delete 
.. autofunction:: update 
.. autofunction:: opt_in 
.. autofunction:: close_out 
.. autofunction:: clear_state 
    


Multiple Bare Handlers
^^^^^^^^^^^^^^^^^^^^^^

If a method requires handling multiple ``OnComplete`` actions, use ``bare_handler``

.. autofunction:: bare_handler
