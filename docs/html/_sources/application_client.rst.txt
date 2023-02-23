Application Client
===================

.. currentmodule:: beaker.client


.. _application_client:

The ``ApplicationClient`` provides a convenient way to interact with our ``Application``.

.. literalinclude:: ../../examples/client/main.py
    :lines: 67-70

By passing an ``AlgodClient``, an instance of our ``Application`` and a ``TransactionSigner``, we can easily make calls to our application. 

.. note::
    The ``ApplicationClient`` takes an ``AlgodClient`` as its first argument, the most common API providers are available in ``beaker.client.api_providers``


If the application does not yet exist, the ``app_id`` argument can be omitted but the first interaction with the ``Application`` should be to ``create`` it. Once this is done, the ``app_id`` will be set for the lifetime of the ``ApplicationClient`` instance.

.. literalinclude:: ../../examples/client/main.py
    :lines: 73-73 

The primary way to of interact with our application is done using the ``call`` method, passing the method we want to call and the arguments it expects as keyword arguments.  

.. literalinclude:: ../../examples/client/main.py
    :lines: 80-80


If there are multiple signers or you want to re-use some suggested parameters, the ``prepare`` method may be called with the different arguments and a copy of the client is returned with the updated parameters.

.. literalinclude:: ../../examples/client/main.py
    :lines: 84-84


:ref:`Full Example <app_client_example>`

.. autoclass:: ApplicationClient
    :members:

.. _app_client_example:

Full Example
-------------

.. literalinclude:: ../../examples/client/main.py
