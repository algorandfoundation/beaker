State
=====

.. module:: beaker

Applications that need to maintain state can declare the state they need as part of the Application. 



.. _application_state:

Application State
-----------------

Algorand refers to Application level state as ``Global State``. 


.. autoclass:: ApplicationState



.. _application_state_value:

Application State Value
^^^^^^^^^^^^^^^^^^^^^^^


.. autoclass:: ApplicationStateValue

.. _dynamic_application_state_value:

Dynamic Application State Value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: DynamicApplicationStateValue


.. _account_state:

Account State
-------------

If your application requires storage of state at the Account level, AccountState may be used.

.. autoclass:: AccountState

.. _account_state_value:

AccountStateValue
^^^^^^^^^^^^^^^^^

.. autoclass:: AccountStateValue


DynamicAccountStateValue
^^^^^^^^^^^^^^^^^^^^^^^^

.. _dynamic_account_state_value:

.. autoclass:: DynamicAccountStateValue

.. literalinclude:: ../../examples/account_state/contract.py