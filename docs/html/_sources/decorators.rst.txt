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

Now lets write a new method to allow any account that is opted in to call it:

.. code-block:: python
    
    from beaker import Authorize

    # ...

    @external(authorize=Authorize.opted_in())
    def vote(self, approve: abi.Bool):
        # ...

This authorize check will cause the contract call to fail if the sender has not opted in to the app. Another app id may also be passed in case you want to check if the Sender is opted in to a different application.

The pre-defined Authorized checks are: 

.. automethod:: Authorize.only
.. automethod:: Authorize.holds_token
.. automethod:: Authorize.opted_in


But we can define our own

.. code-block:: python

    from beaker.consts import Algos

    @Subroutine(TealType.uint64)
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



.. _oncomplete_externals:

OnComplete Externals 
---------------------

If a method expects the ``ApplicationCallTransaction`` to have an  ``OnComplete`` other than ``NoOp``, one of the other ``OnComplete`` decorators may be used instead of ``external`` with a method config set.


OnComplete Decorators 
^^^^^^^^^^^^^^^^^^^^^

.. autodecorator:: create
.. autodecorator:: delete 
.. autodecorator:: update 
.. autodecorator:: opt_in 
.. autodecorator:: close_out 
.. autodecorator:: clear_state 

The ARC4 spec allows applications to define externals for ``bare`` methods, that is methods with no application arguments. 

Routing for ``bare`` methods is based on the transaction's ``OnComplete`` and whether or not it's a Create transaction.

The same handlers described above will also work for ``bare`` method calls but multiple ``OnComplete`` values can be handled with the ``bare_external`` decorator.


Multiple Bare externals
^^^^^^^^^^^^^^^^^^^^^^^^

If a method requires handling multiple ``OnComplete`` actions, use ``bare_external``

.. autodecorator:: bare_external
