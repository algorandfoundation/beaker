State
=====

.. currentmodule:: beaker.state

Applications that need to maintain state can declare the state they need as part of the Application. 

See the `developer docs <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ for details.

:ref:`Full Example <state_example>`

.. _application_state:

Application State
-----------------

Application State holds the stateful values for the Application. Algorand refers to this state as ``Global State``. 


The ``ApplicationState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: ApplicationState

    .. automethod:: dictify
    .. automethod:: initialize
    .. automethod:: schema 

.. _application_state_value:

Application State Value
^^^^^^^^^^^^^^^^^^^^^^^


.. autoclass:: ApplicationStateValue

    .. automethod:: set 
    .. automethod:: increment
    .. automethod:: decrement

    .. automethod:: get
    .. automethod:: get_maybe
    .. automethod:: get_must
    .. automethod:: get_else

    .. automethod:: delete

    .. automethod:: is_default 



.. _dynamic_application_state_value:

Dynamic Application State Value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: DynamicApplicationStateValue

    .. automethod:: __getitem__




.. _account_state:

Account State
-------------

If your application requires storage of state at the Account level, declare the state values at the ``class`` level and the Application class will detect them on initialization. 
Algorand refers to Account state as `Local State`

The ``AccountState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: AccountState

    .. automethod:: dictify
    .. automethod:: initialize
    .. automethod:: schema

.. _account_state_value:

AccountStateValue
^^^^^^^^^^^^^^^^^

.. autoclass:: AccountStateValue

    .. automethod:: set 

    .. automethod:: get
    .. automethod:: get_maybe
    .. automethod:: get_must
    .. automethod:: get_else

    .. automethod:: delete

    .. automethod:: is_default 


DynamicAccountStateValue
^^^^^^^^^^^^^^^^^^^^^^^^

.. _dynamic_account_state_value:

.. autoclass:: DynamicAccountStateValue

    .. automethod:: __getitem__



.. _state_example:

Full Example
------------

.. literalinclude:: ../../examples/state/contract.py