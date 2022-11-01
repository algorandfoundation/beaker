Application Client
===================

.. currentmodule:: beaker.client


.. _application_client:

The ``ApplicationClient`` provides a convenient way to interact with our ``Application``.

.. note::
    The ``ApplicationClient`` takes an ``AlgodClient`` as its first argument, the most common API providers are available in ``beaker.client.api_providers``

:ref:`Full Example <app_client_example>`

The main point of interaction with our application is done using ``call``.  

If there is an application already deployed, the ``app_id`` can be passed during initialization. If no ``app_id`` is passed, it's set to 0 so any app calls will be interpreted by the network as an intention to create the application. Once the ``create`` method is called the app id is set internally to the newly deployed application id and follow up calls will use that id.

If there are multiple signers or you want to re-use some suggested parameters, the ``prepare`` method may be called with the different arguments and a copy of the client is returned with the updated parameters.

.. autoclass:: ApplicationClient

    .. automethod:: call 
    .. automethod:: add_method_call
    .. automethod:: prepare
    .. automethod:: create
    .. automethod:: delete
    .. automethod:: update 
    .. automethod:: opt_in 
    .. automethod:: close_out 
    .. automethod:: clear_state 
    .. automethod:: fund
    .. automethod:: get_application_state 
    .. automethod:: get_application_account_info
    .. automethod:: get_account_state 


.. _app_client_example:

Full Example
-------------

.. literalinclude:: ../../examples/client/main.py
