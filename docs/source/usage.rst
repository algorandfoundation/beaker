Usage
=====

.. _tutorial:

Tutorial
---------


Lets write a bad calculator app. The full source is available `here <https://github.com/algorand-devrel/beaker/blob/master/examples/simple/calculator.py>`_.

First, create a class to represent our application as a subclass of the beaker `Application`. 

.. code-block:: python

    from beaker import Application

    class Calculator(Application):
        pass 


This is a full application, though it doesn't do much.  Instantiate it and take a look at some of the resulting fields. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 61-66


Nice!  This is already enough to provide the TEAL programs and ABI specification.

Lets add some methods to be handled by an incoming ``ApplicationCallTransaction``.  
We can do this by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/>`_ method with with the :ref:`external <external>` decorator. 


.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 9-15


The ``@external`` decorator adds an ABI method with signature ``add(uint64,uint64)uint64`` to our application and includes it in the routing logic for handling an ABI call. 

The python method must return an ``Expr`` of some kind, invoked when the external is called. 

.. note::
    ``self`` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like ``MySickApp.do_thing(data)``

Lets now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 33-48


Thats it! 

To summarize, we:

 * Wrote an application using Beaker and PyTeal
    By subclassing ``Application`` and adding an ``external`` method
 * Compiled it to TEAL 
    Done automatically by Application, PyTeal's ``Router.compile`` 
 * Assembled the TEAL to binary
    Done automatically by the ApplicationClient by sending the TEAL to the Algod ``compile`` endpoint
 * Created the application on chain
    Done by invoking the ``app_client.create``, which takes our binary and submits an ApplicationCallTransaction.

    .. note:: 
        Once created, subsequent calls to the app_client are directed to the ``app_id``. 
        The constructor may also be passed an app_id directly if one is already deployed.

 * Called the method we defined
    Using ``app_client.call``, passing the method defined in our class and args the method specified (by name). 

    .. note::
        The args passed must match the type of the method (i.e. don't pass a string when it wants an int). 

    The result contains the parsed ``return_value`` which should match the type the ABI method returns.


.. _manage_state:

State Management
----------------

Beaker provides a way to define state values as class variables and use them throughout our program. This is a convenient way to encapsulate functionality associated with some state values.

.. note:: 
    Throughout the examples, we tend to mark State Values as ``Final[...]``, this is solely for good practice and has no effect on the output of the program.


Lets write a new app with Application State (or `Global State <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ in Algorand parlance) to our Application. 

.. literalinclude:: ../../examples/simple/counter.py
    :lines: 14-40

We've added an :ref:`ApplicationStateValue <application_state_value>` attribute to our class with several configuration options and we can reference it by name throughout our application.

.. note:: 
    The base ``Application`` class has several externals pre-defined, including ``create`` which performs ``ApplicationState`` initialization for us, setting the keys to default values.

You may also define state values for applications, called :ref:`AccountState <account_state>` (or Local storage) and even allow for dynamic state keys.

For more example usage see the example :ref:`here <state_example>`.

.. _inheritance:

Inheritance 
-----------

What about extending our Application with some other functionality?

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 7-29

Here we subclassed the ``OpUp`` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.

We inherit the methods and class variables that ``OpUp`` defined, allowing us to encapsulate and compose behavior.