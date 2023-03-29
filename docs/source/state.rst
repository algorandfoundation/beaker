State
=====

.. currentmodule:: beaker.state

Applications that need to maintain state can declare the state they need by passing an instance of a class where the State values have been defined as attributes. 

See the `developer docs <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ for details.

See the `Parameters Table <https://developer.algorand.org/docs/get-details/parameter_tables/>`_ for protocol level limits on State.

.. warning::
    The ``static`` option on state values is enforced only when using the methods provided by the objects described here. 
    It is still possible to overwrite or delete the values using the accessors provided by PyTeal or TEAL directly.


.. warning::
    When using the ``GlobalStateBlob`` or ``LocalStateBlob``, the keys used to store data are 1 byte in the range [0-255]. Care must be taken to prevent any other state values from overwriting those keys.
    For example if ``ReservedLocalStateValue`` tries to write to key ``0x00`` and a blob is already using that key, bad things will happen.


For documentation on box storage please see the :ref:`Boxes <Boxes>` page

.. _state_declaration:

State Declaration
------------------

State is declared by passing an instance of a class where the State values have been defined as attributes.

Declaration of state:

.. code-block:: python

    class DemoState:
        global_state_value = GlobalStateValue(TealType.uint64)
        local_state_value = LocalStateValue(TealType.bytes)

    app = Application("StatefulApp", state=DemoState())


Usage in app logic:

.. code-block:: python

    # ...
    # Set the value in the `global_state_value` we declared
    app.state.global_state_value.set(Int(123))
    # ...
    


:ref:`Full Example <state_example>`

.. _global_state:

Global State
------------

Global State holds the stateful values for the Application. 


.. _global_state_value:

Global State Value
^^^^^^^^^^^^^^^^^^^

.. autoclass:: GlobalStateValue
    :members:


.. _reserved_global_state_value:

Reserved Global State Value
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: ReservedGlobalStateValue
    :members:


.. _global_state_blob:

Global State Blob
^^^^^^^^^^^^^^^^^^^

.. autoclass:: GlobalStateBlob
    :members:


.. _local_state:

Local State
------------

If your application requires storage of state at the Account level, the state values can be declared in the same was as Global State above. 

LocalStateValue
^^^^^^^^^^^^^^^

.. autoclass:: LocalStateValue
    :members:


.. _reserved_local_state_value:

ReservedLocalStateValue
^^^^^^^^^^^^^^^^^^^^^^^

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