State
=====

.. currentmodule:: beaker.state

Applications that need to maintain state can declare the state they need as part of the Application. 

See the `developer docs <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ for details.

.. warning::
    The ``static`` option on state values is enforced only when using the methods provided by the objects described here. It is still possible to overwrite or delete the values using the accessors provided by PyTeal or TEAL directly.

.. warning::
    When using the ``ApplicationStateBlob`` or ``AccountStateBlob``, the keys used to store data are 1 byte in the range [0-255]. Care must be taken to prevent any other state values from overwriting those keys.
    For example if ``ReservedAccountStateValue`` tries to write to key ``0x00`` and a blob is already using that key, bad things will happen.


:ref:`Full Example <state_example>`

.. _application_state:

Application State
-----------------

Application State holds the stateful values for the Application. Algorand refers to this state as ``Global State``. 

The ``ApplicationState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: ApplicationState
    :members:

.. _application_state_value:

Application State Value
^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ApplicationStateValue
    :members:


.. _reserved_application_state_value:

Reserved Application State Value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ReservedApplicationStateValue
    :members:


.. _application_state_blob:

Application State Blob 
^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ApplicationStateBlob
    :members:


.. _account_state:

Account State
-------------

If your application requires storage of state at the Account level, declare the state values at the ``class`` level and the Application class will detect them on initialization. 
Algorand refers to Account state as `Local State`

The ``AccountState`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: AccountState
    :members:

.. _account_state_value:

AccountStateValue
^^^^^^^^^^^^^^^^^

.. autoclass:: AccountStateValue
    :members:


.. _reserved_account_state_value:

ReservedAccountStateValue
^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ReservedAccountStateValue
    :members:


.. _account_state_blob:

Account State Blob 
^^^^^^^^^^^^^^^^^^^

.. autoclass:: AccountStateBlob
    :members:


.. _state_example:

Full Example
------------

.. literalinclude:: ../../examples/state/contract.py