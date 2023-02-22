State
=====

.. warning:: Out of date, needs to be updated to 1.0

.. currentmodule:: beaker.state

Applications that need to maintain state can declare the state they need as part of the Application. 

See the `developer docs <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ for details.

.. warning::
    The ``static`` option on state values is enforced only when using the methods provided by the objects described here. It is still possible to overwrite or delete the values using the accessors provided by PyTeal or TEAL directly.

.. warning::
    When using the ``GlobalStateBlob`` or ``LocalStateBlob``, the keys used to store data are 1 byte in the range [0-255]. Care must be taken to prevent any other state values from overwriting those keys.
    For example if ``ReservedLocalStateValue`` tries to write to key ``0x00`` and a blob is already using that key, bad things will happen.


:ref:`Full Example <state_example>`

.. _application_state:

Global State
-----------------

Global State holds the stateful values for the Application. Algorand refers to this state as ``Global State``.

The ``GlobalStateStorage`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: GlobalStateStorage
    :members:

.. _global_state_value:

Global State Value
^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: GlobalStateValue
    :members:


.. _reserved_global_state_value:

Reserved Global State Value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ReservedGlobalStateValue
    :members:


.. _global_state_blob:

Global State Blob
^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: GlobalStateBlob
    :members:


.. _local_state:

Local State
-------------

If your application requires storage of state at the Account level, declare the state values at the ``class`` level and the Application class will detect them on initialization. 
Algorand refers to Account state as `Local State`

The ``LocalStateStorage`` class is produced automatically by the ``Application``, there is no need to create it directly.

.. autoclass:: LocalStateStorage
    :members:

.. _account_state_value:

LocalStateValue
^^^^^^^^^^^^^^^^^

.. autoclass:: LocalStateValue
    :members:


.. _reserved_local_state_value:

ReservedLocalStateValue
^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ReservedLocalStateValue
    :members:


.. _local_state_blob:

Local State Blob
^^^^^^^^^^^^^^^^^^^

.. autoclass:: LocalStateBlob
    :members:


.. _state_example:


Full Example
------------

.. literalinclude:: ../../examples/state/contract.py