Usage
=====

.. _tutorial:

Tutorial
---------

.. note::
    This tutorial assumes you've already installed the `sandbox <https://github.com/algorand/sandbox>`_ and have it running. 


Lets write a simple calculator app.  `Full source here <https://github.com/algorand-devrel/beaker/blob/master/examples/simple/calculator.py>`_.

First, create an instance of the ``Application`` class to represent our application. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 4-6

This is a full application, though it doesn't do much.  

Build it and take a look at some of the resulting fields. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 65-68


Nice!  This is already enough to provide the TEAL programs and ABI specification.

.. note::
    The ``Application.export`` method can be used to write the ``approval.teal``, ``clear.teal``, ``contract.json``, and ``application.json`` to the local file system.

Lets add some methods to be handled by an incoming `ApplicationCallTransaction <https://developer.algorand.org/docs/get-details/transactions/transactions/#application-call-transaction>`_.  
We can do this by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/api.html#pyteal.ABIReturnSubroutine>`_ method with with the :ref:`external <external>` decorator. 


.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 8-30


The ``@Application.external`` decorator adds an ABI method to our application and includes it in the routing logic for handling an ABI call. 

The python method __must__ return an ``Expr`` of some kind, invoked when the external is called. 

Lets now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 33-48


Thats it! 

To summarize, we:

 * Wrote an application using Beaker and PyTeal
    By instantiating a new ``Application`` and adding ``external`` methods
 * Built the smart contract, converting it to TEAL 
    Done by calling the ``build`` method on by the ``Application`` class
 * Assembled the TEAL to binary
    Done automatically by the ``ApplicationClient`` by sending the TEAL to the algod ``compile`` endpoint
 * Deployed the application on-chain
    Done by invoking the ``app_client.create``, which submits an ``ApplicationCallTransaction`` including our compiled programs.

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

It is also possible to use one of the :ref:`OnComplete <oncomplete_externals>` decorators (e.g. ``create``, ``opt_in``, etc...) to specify a single ``OnComplete`` type the contract expects. 


.. _manage_state:

State Management
----------------

Beaker provides a way to define state in terms of a class which encapsulates the state configuration. This provides a convenient way to organize and reference state values.

Lets write a new app, adding Global State to our Application. 

.. literalinclude:: ../../examples/simple/counter.py
    :lines: 12-40

We've created a class to hold our State and added a :ref:`GlobalStateValue <global_state_value>` attribute to it with configuration options for how it should be treated. We can reference it by name throughout our application.

You may also define state values for applications, called :ref:`LocalState <local_state>` (or Local storage) and even allow for reserved state keys when you're not sure what the keys will be.

For more example usage see the example :ref:`here <state_example>`.

.. _code_reuse:

Code Reuse 
-----------

What about extending our Application with some other functionality that we've already written?

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 18-26

Here we call a method ``op_up_blueprint`` passing our application instance. This method attaches some extra handlers to our app and returns a method that can be called in our app. 


.. _parameter_default:

Parameter Default Values
------------------------

In the ``OpUp`` example, there is a method handler ``hash_it`` which specifies the argument ``opup_app`` should be the ID of the application that we use to increase our budget via inner app calls.  

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 29-36


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

Often an app developer needs to have the assembled binary of a program available at contract runtime. One way to get this binary is to use the ``precompile`` feature.

In the ``OpUp`` example, the ``ExpensiveApp`` needs to create an application to use as the target app for op budget increase calls.

.. literalinclude:: ../../examples/opup/op_up.py
    :lines: 55-71

The inclusion of a ``precompile`` prevents building the TEAL for the containing Application until the ``precompile`` been fully compiled to assembled binary but we can still reference it in our Application.

Another situations where a ``precompile`` is useful is when validating the logic of a ``LogicSignature``.

In the ``offload_compute`` example, we check to make sure that the address of the signer is the ``LogicSignature`` we're expecting so that we're sure it is doing "the right thing".

.. literalinclude:: ../../examples/offload_compute/main.py
    :lines: 23-43

Additionally, if the ``LogicSignature`` needs one or more ``TemplateVariables`` the ``LogicSignatureTemplate`` is used and functions similarly, by passing the named template arguments to the call to get the ``address``.

.. literalinclude:: ../../examples/templated_lsig/main.py
    :lines: 29-60
