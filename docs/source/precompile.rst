Precompile
==========

A ``precompile`` is useful if you need the fully assembled binary representation of a TEAL program in the logic of another TEAL program.

:ref:`One example <offload_compute_example>` of where it might be used, is in offloading some compute into a LogicSignature, 
which has a max opcode budget of 20k ops compared with 700 ops in a single Application call. 

By using the ``precompile`` in this way we can check offload the more expensive computation to the ``LogicSignature`` and preserve the app calls opcode budget for other work. 

.. note::
    When we do this, we need to be careful that the ``LogicSignature`` is the one we expect by checking its address, which is the hash of the program logic.

:ref:`Another example <sub_app_example>` might be if you need to deploy some child Application and want to have the logic 
locally in the program as compiled bytes so the "parent app" can create the "child app" directly in program logic.

By using the ``precompile`` in this way, we can deploy the Sub Application directly from our Parent app.

.. note::
    When we do this, the compiled program will take up more space in our "parent app" contract, so some consideration of the trade offs between program size and convenience may be necessary.

Usage
-----

In order to use a ``Precompile`` in a program, first wrap the ``LogicSignature`` or ``Application`` with the ``precompile`` method. This will ensure that the program is fully compiled once and only once and the binary versions of the assembled programs are available when it's time to build the containing ``Application`` or ``LogicSignature``. 

.. note::
    The ``precompile`` function may _only_ be called inside a function.

.. literalinclude:: ../../examples/nested_precompile/smart_contracts/parent.py
    :lines: 10-17 
    :emphasize-lines: 4


Reference
---------

.. module:: beaker.precompile 

.. autoclass:: PrecompiledApplication
    :members:

.. autoclass:: PrecompiledLogicSignature
    :members:

.. autoclass:: PrecompiledLogicSignatureTemplate
    :members:

Examples
--------

.. _offload_compute_example:

Using Precompile for offloading compute 

.. literalinclude:: ../../examples/offload_compute/eth_checker.py
    :emphasize-lines: 98

.. _sub_app_example:

Using Precompile for a child Application 

.. literalinclude:: ../../examples/nested_precompile/smart_contracts/parent.py
    :emphasize-lines: 13,23