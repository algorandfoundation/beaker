Application Client
===================

.. currentmodule:: beaker.client


The ``ApplicationClient`` provides a convenient way to interact with our ``Application``.

The main point of interaction with our application is done using ``call``.  

If there are multiple signers or you want to re-use some suggested parameters, the ``prepare`` method may be called with the different arguments and a copy of the client is returned with the updated parameters.

.. _application_client:

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
    .. automethod:: get_application_state 
    .. automethod:: get_application_account_info
    .. automethod:: get_account_state 

    