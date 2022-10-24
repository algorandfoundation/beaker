Precompile
==========

A Precompile as an attribute on a Beaker Application allows the contract to 
have some program be included in the source of the applications programs.

:ref:`One example <offload_compute_example>` of where it might be used is in offloading some compute into a LogicSignature
which has a max budget of 20k ops compared with 700 ops in a single Application call. 

:ref:`Another example <sub_app_example>` might be if you need to deploy some child Application and want to have the logic 
locally as compiled bytes to create the app directly in program logic.

When you include an ``AppPrecompile`` or ``LSigPrecompile`` in your Application as a class var, Beaker knows to prevent building the TEAL
until the ``Precompiles`` it depends on are fully assembled. 

This can be done in two ways: 
    1) By passing the top level ``Application`` to an ``ApplicationClient`` and calling the ``build`` method, the top level ``Application`` will have its dependencies fully assembled recursively.
    2) By calling ``compile`` method on the ``AppPrecompile`` or ``LSigPrecompile`` and passing an ``AlgodClient`` to assemble the dependencies.


.. module:: beaker.precompile 

.. autoclass:: AppPrecompile
    :members:

.. autoclass:: LSigPrecompile
    :members:

.. autoclass:: Precompile
    :members:

.. autoclass:: PrecompileTemplateValue
    :members:

Examples
--------

.. _offload_compute_example:

Using Precompile for offloading compute 

.. literalinclude:: ../../examples/offload_compute/main.py
    :lines: 18-39


.. _sub_app_example:

Using Precompile for a child Application 

.. literalinclude:: ../../examples/nested_precompile/nested_application.py