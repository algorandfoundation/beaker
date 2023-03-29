Application Client
===================

.. currentmodule:: beaker.client


.. _application_client:

The ``ApplicationClient`` provides a convenient way to interact with our ``Application``.

.. literalinclude:: ../../examples/client/demo.py
    :lines: 16-19

By passing an ``AlgodClient``, an instance of our ``Application`` and a ``TransactionSigner``, we can easily make calls to our application. 

.. note::
    The ``AlgodClient`` passed to the ``ApplicationClient`` is always one pointing to the local sandbox in examples. This is not a requirement, it can be connected to any ``Algod`` node and the most common API providers are available in ``beaker.client.api_providers``


If the application does not yet exist, the ``app_id`` argument can be omitted but the first interaction with the ``Application`` should be to ``create`` it. 

If ``create`` is called, the ``app_id`` will be set for the lifetime of the ``ApplicationClient`` instance.

If the application **does** exist, the app_id can be provided directly 

.. literalinclude:: ../../examples/client/demo.py
    :lines: 70-76
    :emphasize-lines: 6

The primary way to interact with our application is by using the ``call`` method, passing the method we want to call and the arguments it expects as keyword arguments.  

.. literalinclude:: ../../examples/client/demo.py
    :lines: 31-31 

If multiple app calls are required in the same atomic group, the ``ApplicationClient`` also allows composing a group of calls using the ``add_method_call`` method which uses an ``AtomicTransactionComposer`` to build the group.

If there are multiple signers, or you want to re-use some suggested parameters, the ``prepare`` method may be called with the different arguments and a copy of the client is returned with the updated parameters.

.. literalinclude:: ../../examples/client/demo.py
    :lines: 35-35


:ref:`Full Example <app_client_example>`

.. autoclass:: ApplicationClient
    :members:

.. _app_client_example:

Full Example
-------------

.. literalinclude:: ../../examples/client/demo.py
