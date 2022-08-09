Decorators
===========

Beaker uses decorated methods to apply configurations to the methods they decorate.  The configuration allows the ``Application`` class to know how to expose them.


.. module:: beaker.decorators

.. _external:

ABI Method external
--------------------

The ``external`` decorator is how we can add methods to be handled as ABI methods. 

Tagging a method as ``external`` adds it to the internal ``Router`` with whatever configuration is passed, if any.

.. autodecorator:: external



.. _authorization:

Authorization
^^^^^^^^^^^^^

Often, we would like to restrict the accounts that may call certain methods. 

.. autoclass:: Authorize


Lets add a parameter to the external to allow only the app creator to call this method.

.. code-block:: python

    from beaker import Authorize

    #...

    @external(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter)
        )

The ``authorize`` parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  

The pre-defined Authorized checks are: 

.. automethod:: Authorize.only
.. automethod:: Authorize.holds_token
.. automethod:: Authorize.opted_in


But we can define our own

.. code-block:: python

    from beaker.consts import Algos

    @internal(TealType.uint64)
    def is_whale(acct: Expr):
        # Only allow accounts with 1mm algos
        return Balance(acct)>Algos(1_000_000)

    @external(authorize=is_whale)
    def greet(*, output: abi.String):
        return output.set("hello whale")



.. _method_hints:

Method Hints
^^^^^^^^^^^^

.. autoclass:: MethodHints
    :members:


.. _resolvable:


.. autoclass:: DefaultArguments

.. warning:: 
    This is EXPERIMENTAL

In an above example, there is a required argument `opup_app`, the id of the application that we use to increase our budget via inner app calls. This value should not change frequently, if at all, but is still required to be passed so we may _use_ it in our logic. We can provide a caller the information to `resolve` the appropriate app id using the `resolvable` keyword argument of the external. 

We can change the external to provide the hint.

.. code-block:: python

    @external(
        resolvable=DefaultArguments(
            opup_app=OpUp.opup_app_id 
        )
    )

With this external config argument, we communicate to a caller the application expects be passed a value that can bee resolved by retrieving the state value in the application state for `opup_app_id`.  This allows the `ApplicationClient` to figure out what the appropriate application id _should_ be if necessary. 

Options for resolving arguments are:

- A constant, `str | int`
- State Values, `ApplicationStateValue | AccountStateValue`
- A read-only ABI method  


Here we call the method, omitting the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the `ApplicationClient` consults the method definition to check that all the expected arguments are passed. If it finds one missing, it will check for hints for the method that may be resolvable. Upon finding a resolvable it will look up the state value, call the method, or return the constant value. The resolved value is passed in for argument.


.. _read_only:

**Read Only**

Methods that are meant to only produce information, having no side effects, should be flagged as read only. 

See `ARC22 <https://github.com/algorandfoundation/ARCs/pull/79>`_ for more details.

.. code-block:: python

    count = ApplicationStateValue(stack_type=TealType.uint64) 

    @external(read_only=True)
    def get_count(self, id_of_thing: abi.Uint8, *, output: abi.Uint64):
        return output.set(self.count)


.. _internal_methods:

Internal Methods
----------------

An Application will often need a number of internal ``utility`` type methods to handle common logic.  
We don't want to expose these methods to the ABI but we do want to allow them to access any instance variables.

.. note:: 
    If you want some method to return the expression only and not be triggered with ``callsub``, omit the ``@internal`` decorator and the expression will be inlined 


.. autodecorator:: internal

.. code-block:: python

    @internal(TealType.uint64)
    def do_logic(self):
        return If(self.counter>10, self.send_asset())



.. _bare_externals:

Bare externals
---------------

The ARC4 spec allows applications to define externals for ``bare`` methods, that is methods with no application arguments. 

Routing for ``bare`` methods is based on the transaction's ``OnComplete`` and whether or not it's a Create transaction.

Single Bare externals
^^^^^^^^^^^^^^^^^^^^^^

If a single OnComplete should be handled by a given method, use one of the pre-defined helpers.

.. autodecorator:: create
.. autodecorator:: delete 
.. autodecorator:: update 
.. autodecorator:: opt_in 
.. autodecorator:: close_out 
.. autodecorator:: clear_state 
    


Multiple Bare externals
^^^^^^^^^^^^^^^^^^^^^^^^

If a method requires handling multiple ``OnComplete`` actions, use ``bare_external``

.. autodecorator:: bare_external
