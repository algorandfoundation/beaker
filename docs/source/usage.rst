Usage
=====

.. _tutorial:

Tutorial
---------

.. note::
    This tutorial assumes you've already got a local ``algod`` node running from either `Algokit <https://github.com/algorandfoundation/algokit-cli>`_ or the `sandbox <https://github.com/algorand/sandbox>`_. 


Let's write a simple calculator app.  `Full source here <https://github.com/algorand-devrel/beaker/blob/master/examples/simple/calculator.py>`_.

First, create an instance of the ``Application`` class to represent our application. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 6-6

This is a full application, though it doesn't do much.  

Build it and take a look at the resulting application spec. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 64-67


Great! This is already enough to provide the TEAL programs and ABI specification.

.. note::
    The ``Application.export`` method can be used to write the ``approval.teal``, ``clear.teal``, ``contract.json``, and ``application.json`` to the local file system.

Let's now add some methods to be handled by an incoming `ApplicationCallTransaction <https://developer.algorand.org/docs/get-details/transactions/transactions/#application-call-transaction>`_.  
We can do this by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/api.html#pyteal.ABIReturnSubroutine>`_ method with the ``external`` decorator. 


.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 9-30


The ``@Application.external`` decorator adds an ABI method to our application and includes it in the routing logic for handling an ABI call. 

.. note::
    The python method **must** return a PyTeal ``Expr``, to be invoked when the external method is called. 

Let's now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 33-50


That's it! 

To summarize, we:

 * Wrote an application using Beaker and PyTeal
    By instantiating a new ``Application`` and adding ``external`` methods.
 * Built the smart contract, converting it to TEAL 
    Done by calling the ``build`` method on by the ``Application`` instance.
 * Assembled the TEAL to binary
    Done automatically by the ``ApplicationClient`` during initialization by sending the TEAL to the algod ``compile`` endpoint.
 * Deployed the application on-chain
    Done by invoking the ``app_client.create``, which submits an ``ApplicationCallTransaction`` including our compiled programs.

    .. note:: 
        Once created, subsequent calls to the app_client are directed to the ``app_id``. 
        The constructor may also be passed an ``app_id`` directly if one is already deployed.

 * Called the method we defined
    Using ``app_client.call``, passing the method defined in our class and args the method specified as keyword arguments. 

    .. note::
        The args passed must match the types of those specified in of the method (i.e. don't pass a string when it wants an int). 

    The result contains the parsed ``return_value`` which is a python native type that reflects the return type of the ABI method.

.. _use_decorators: 

Decorators
-----------

Above, we used the decorator ``@app.external`` to mark a method as being exposed in the ABI and available to be called from off-chain.

The ``@external`` decorator can take parameters to change how it may be called or what accounts may call it.

It is also possible to use one of the ``OnComplete`` decorators (e.g. ``update``, ``delete``, ``opt_in``, etc...) to specify a single ``OnComplete`` type the contract expects. 


.. _manage_state:

State Management
----------------

Beaker provides a way to define state using a class which encapsulates the state configuration. This provides a convenient way to organize and reference state values.

Let's write a new app, adding Global State to our Application. 

.. literalinclude:: ../../examples/simple/counter.py
    :lines: 12-39

We've created a class to hold our State and added a :ref:`GlobalStateValue <global_state_value>` attribute to it with configuration options for how it should be treated. We can reference it by name throughout our application.

You may also define state values for applications, called :ref:`LocalState <local_state>` (or Local storage) and even allow for reserved state keys when you're not sure what the keys will be.

For more example usage see the example :ref:`here <state_example>`.

.. _code_reuse:

Code Reuse 
-----------

What about extending our Application with some functionality that already exists? For example, what if we wanted to provide the correct interface for a specific ARC?

We can use the ``blueprint`` pattern to include things like method handlers to our application! 

.. literalinclude:: ../../examples/blueprint/main.py
    :lines: 10-28

Here we add a method handler for an ABI method to our application in two ways.

If no arguments are needed for the blueprint method, we can pass it to ``apply`` and the blueprint method will be called with our ``Application`` as the argument.

.. literalinclude:: ../../examples/blueprint/main.py
    :lines: 18-18

If the blueprint requires some arguments to customize it's behavior, we can pass the additional arguments the blueprint expects:

.. literalinclude:: ../../examples/blueprint/main.py
    :lines: 28-28


.. _parameter_default:

Parameter Default Values
------------------------

In the ``OpUp`` example, there is a method handler, ``hash_it``, which specifies the argument ``opup_app`` should be the ID of the application that we use to increase our budget via inner app calls.  

.. note::
    The default argument shown below is _not_ a valid type, it's only used as a hint to the compiler. If you're using mypy or similar, a type ignore directive should be used to stop it from complaining. 

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 20-36
    :emphasize-lines: 5


This value should not change frequently, if at all, but is still required to be passed by the caller, so we may **use** it in our logic.

By specifying the default value of the argument in the method signature, we can communicate to the caller, through the hints of the Application Specification, what the value **should** be. 

Options for default arguments are:

- A constant: one of ``bytes | int | str | Bytes | Int``
- State Values: one of ``GlobalStateValue | LocalStateValue``
- A **read-only** ABI method: a method defined to produce some more complex value than a state value or constant would be able to produce.


The result of specifying the default value here, is that we can call the method without specifying the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the ``ApplicationClient`` consults the Application Specification to check that all the expected arguments are passed. 

If it finds that an argument the method expects is not passed, it will check the hints for a default value for the argument of the method that may be used directly (constant) or resolved (need to look it up on chain or call method). 

Upon finding a default value that needs to be resolved, it will look up the state value or call the method. The resulting value is passed in for argument to the application call.


Precompiles
-----------

Often an app developer needs to have the fully assembled binary of a program available at contract runtime. One way to get this binary is to use the ``precompile`` feature.

In the ``OpUp`` example, the ``ExpensiveApp`` needs to create an application to use as the target app for op budget increase calls.

.. literalinclude:: ../../examples/opup/op_up.py
    :lines: 39-55
    :emphasize-lines: 5

Another situations where a ``precompile`` is useful is when validating the logic of a ``LogicSignature``.

In the ``offload_compute`` example, we check to make sure that the address of the signer is the ``LogicSignature`` we're expecting so that we're sure it is doing "the right thing".

.. literalinclude:: ../../examples/offload_compute/eth_checker.py
    :lines: 86-106
    :emphasize-lines: 19 

Additionally, if the ``LogicSignature`` needs one or more ``TemplateVariables`` the ``LogicSignatureTemplate`` is used and functions similarly, by passing the named template arguments to the call to get the ``address``.

.. literalinclude:: ../../examples/templated_lsig/sig_checker.py
    :lines: 31-40
    :emphasize-lines: 9
