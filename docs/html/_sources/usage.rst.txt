Usage
=====

.. _tutorial:

Tutorial
---------

.. note::
    This tutorial assumes you've already installed the `sandbox <https://github.com/algorand/sandbox>`_ and have it running. 


Lets write a simple calculator app.  `Full source here <https://github.com/algorand-devrel/beaker/blob/master/examples/simple/calculator.py>`_.

First, create a class to represent our application as a subclass of the beaker `Application`. 

.. code-block:: python

    from beaker import Application

    class Calculator(Application):
        pass 


This is a full application, though it doesn't do much.  

Instantiate it and take a look at some of the resulting fields. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 59-62


Nice!  This is already enough to provide the TEAL programs and ABI specification.

.. note::
    The ``Application.dump`` method can be used to write the ``approval.teal``, ``clear.teal``, ``contract.json``, and ``application.json`` to the local file system.

Lets add some methods to be handled by an incoming `ApplicationCallTransaction <https://developer.algorand.org/docs/get-details/transactions/transactions/#application-call-transaction>`_.  
We can do this by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/api.html#pyteal.ABIReturnSubroutine>`_ method with with the :ref:`external <external>` decorator. 


.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 9-28


The ``@external`` decorator adds an ABI method to our application and includes it in the routing logic for handling an ABI call. 

The python method must return an ``Expr`` of some kind, invoked when the external is called. 

.. note::
    ``self`` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like ``MySickApp.do_thing(data)``

Lets now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 32-46


Thats it! 

To summarize, we:

 * Wrote an application using Beaker and PyTeal
    By subclassing ``Application`` and adding an ``external`` method
 * Compiled it to TEAL 
    Done automatically by the ``Application`` class, and PyTeal's ``Router.compile`` 
 * Assembled the TEAL to binary
    Done automatically by the ``ApplicationClient`` by sending the TEAL to the algod ``compile`` endpoint
 * Deployed the application on-chain
    Done by invoking the ``app_client.create``, which submits an ApplicationCallTransaction including our binary.

    .. note:: 
        Once created, subsequent calls to the app_client are directed to the ``app_id``. 
        The constructor may also be passed an app_id directly if one is already deployed.

 * Called the method we defined
    Using ``app_client.call``, passing the method defined in our class and args the method specified (by name). 

    .. note::
        The args passed must match the type of the method (i.e. don't pass a string when it wants an int). 

    The result contains the parsed ``return_value`` which is a python native type that mirrors the return type of the ABI method.

.. _use_decorators: 

Decorators
-----------

Above, we used the decorator ``@external`` to mark a method as being exposed in the ABI and available to be called from off-chain.

The ``@external`` decorator can take parameters to change how it may be called or what accounts may call it, see examples :ref:`here <external>`.

Other decorators include :ref:`@internal <internal_methods>` which marks the method as being callable only from inside the application or with one of the :ref:`OnComplete <oncomplete_externals>` handlers (e.g. ``create``, ``opt_in``, etc...)


.. _manage_state:

State Management
----------------

Beaker provides a way to define state values as class variables and use them throughout our program. This is a convenient way to encapsulate functionality associated with some state values.

.. note:: 
    Throughout the examples, we tend to mark State Values as ``Final[...]``, this is solely for good practice and has no effect on the output of the program.


Lets write a new app with Application State (or `Global State <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ in Algorand parlance) to our Application. 

.. literalinclude:: ../../examples/simple/counter.py
    :lines: 12-38

We've added an :ref:`ApplicationStateValue <application_state_value>` attribute to our class with several configuration options and we can reference it by name throughout our application.

.. note:: 
    The base ``Application`` class has several externals pre-defined, including ``create`` which performs ``ApplicationState`` initialization for us, setting the keys to default values.

You may also define state values for applications, called :ref:`AccountState <account_state>` (or Local storage) and even allow for reserved state keys.

For more example usage see the example :ref:`here <state_example>`.

.. _inheritance:

Inheritance 
-----------

What about extending our Application with some other functionality?

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 4-29

Here we subclassed the ``OpUp`` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.

We inherit the methods and class variables that ``OpUp`` defined, allowing us to encapsulate and compose behavior.

Also note that the ``opup_app`` argument specifies a default value. This is a bit of magic that serves only to produce a hint for the caller in the resulting Application Spec.

.. _parameter_default:

Parameter Default Values
------------------------

In the ``OpUp`` example above, the argument ``opup_app`` should be the id of the application that we use to increase our budget via inner app calls.  
This value should not change frequently, if at all, but is still required to be passed by the caller so we may **use** it in our logic, namely to execute an application call against it. 

By specifying the default value of the argument in the method signature, we can communicate to the caller, through the hints of the Application Spec, what the value **should** be. 

Options for default arguments are:

- A constant: one of ``bytes | int | str | Bytes | Int``
- State Values: one of ``ApplicationStateValue | AccountStateValue``
- A read-only ABI method: a method defined to produce some more complex value than a state value or constant would be able to produce.


The result of specifying the default value here is that we can call the method, omitting the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the ``ApplicationClient`` consults the method definition to check that all the expected arguments are passed. 
If it finds that an argument is not passed, it will check the hints for a default argument for the method that may be used directly (constant) or resolved (need to look it up on chain or call method). 
Upon finding a resolvable it will look up the state value, call the method. The resulting value is passed in for argument to the application call.


Precompiles
-----------

Often an app developer needs to have the assembled binary of a program available at contract runtime. One way to get this binary is to use the ``Precompile`` feature.

In the ``OpUp`` example above, the ``ExpensiveApp`` inherits from the ``OpUp`` app. The ``OpUp`` app contains an ``AppPrecompile`` for the target app we'd like to call 
when we make opup requests.

.. literalinclude:: ../../examples/opup/op_up.py
    :lines: 28-41

The inclusion of a ``Precompile`` prevents building the TEAL until its been fully compiled to assembled binary but we can still reference it in our Application.

The ``OpUp`` Application defines a method to create the target application by referencing the ``AppPrecompile's`` approval/clear binary attribute which contains the assembled binary 
for the target Application as a ``Bytes`` Expression.

.. literalinclude:: ../../examples/opup/op_up.py
    :lines: 59-74

Another situations where a ``Precompile`` is useful is when validating the logic of a LogicSignature.

In the ``offload_compute`` example, we check to make sure that the hash of the signer is the LogicSignature we're expecting so that we're sure it is doing "the right thing".

.. literalinclude:: ../../examples/offload_compute/main.py
    :lines: 28-38 

Additionally, if the LogicSignature has one or more ``TemplateVariables`` specified, the ``template_hash`` function may be used by passing arguments that should be populated into the templated ``LogicSignature``.

.. literalinclude:: ../../examples/templated_lsig/main.py
    :lines: 38-43 



