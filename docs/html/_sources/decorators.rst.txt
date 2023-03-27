Decorators
==========

Beaker Application decorators are used to add method handlers to the Application.

They optionally accept parameters that apply configurations to the methods they decorate.


.. module:: beaker.decorators

.. _authorization:

Authorization
-------------

Often, we would like to restrict the accounts that may call certain methods. 

Let's add a parameter to the ``external`` decorator to prevent anyone but the app creator to call this method.

.. code-block:: python

    from beaker.decorators import Authorize

    #...

    @app.external(authorize=Authorize.only(Global.creator_address()))
    def increment(*, output: abi.Uint64):
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter)
        )

The ``authorize`` parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  

Now let's write a new method to allow any account that is opted in to call it:

.. code-block:: python
    
    from beaker.decorators import Authorize

    # ...

    @app.external(authorize=Authorize.opted_in())
    def vote(approve: abi.Bool):
        # ...

This value passed to ``authorize`` will cause the contract call to fail if the sender has not opted in to the app. Another app ID may be passed in case you want to check if the sender is opted in to a different application.

The pre-defined Authorized checks are: 

.. automethod:: Authorize.only
.. automethod:: Authorize.holds_token
.. automethod:: Authorize.opted_in


But we can define our own

.. code-block:: python

    from pyteal import Subroutine
    from beaker.consts import Algos

    @Subroutine(TealType.uint64)
    def is_whale(acct: Expr):
        # Only allow accounts with 1mm algos
        return Balance(acct)>Algos(1_000_000)

    # ...

    @app.external(authorize=is_whale)
    def greet(*, output: abi.String):
        return output.set("hello whale")

.. _read_only:

Read Only
----------

Methods that are meant to only produce information, having no side effects, should be flagged as read only. 

See `ARC22 <https://arc.algorand.foundation/ARCs/arc-0022>`_ for more details.

.. code-block:: python

    class ROAppState:
        count = ApplicationStateValue(stack_type=TealType.uint64) 

    app = Application("CoolApp", state=ROAppState())

    @app.external(read_only=True)
    def get_count(id_of_thing: abi.Uint8, *, output: abi.Uint64):
        return output.set(app.state.count)


.. _oncomplete_settings:

On Complete
-----------

If a method expects the ``ApplicationCallTransaction`` to have a certain ``OnComplete`` other than ``NoOp``, one of the other ``OnComplete`` decorators may be used instead of ``external`` with a method config set.

.. module:: beaker.application
.. autoclass:: Application
    :noindex:
    :special-members:
    :members: create, delete, update, opt_in, close_out, clear_state

The `ARC4 <https://arc.algorand.foundation/ARCs/arc-0004>`_ spec allows applications to define handlers for ``bare`` methods, that is, methods with no application arguments.  The routing for these methods is based only on the ``OnComplete`` value of the transaction rather than the method selector of the method being invoked.
