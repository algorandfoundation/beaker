State
=====

.. currentmodule:: beaker.state

Applications that need to maintain state can declare the state they need as part of the Application. 


.. _application_state:

Application State
-----------------

Algorand refers to Application level state as ``Global State``. 

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


The ``ApplicationState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: ApplicationState

    .. automethod:: dictify
    .. automethod:: initialize
    .. automethod:: schema 




.. _account_state:

Account State
-------------

If your application requires storage of state at the Account level, declare the state values at the ``class`` level and the Application class will detect them on initialization.

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


The ``AccountState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: AccountState

    .. automethod:: dictify
    .. automethod:: initialize
    .. automethod:: schema

.. _state_example:

Full Example
------------

.. literalinclude:: ../../examples/state/contract.py