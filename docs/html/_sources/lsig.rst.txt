Logic Signatures
================

.. module:: beaker.logic_signature

This is the class that should be initialized to provide a LogicSignature.

A ``LogicSignature`` is intialized with either a PyTeal ``Expr`` or a function that returns an ``Expr``.

.. literalinclude:: ../../examples/offload_compute/eth_checker.py
    :lines: 59-74

A ``LogicSignatureTemplate`` is initialized by passing a PyTeal ``Expr`` or a function that returns an ``Expr`` **and** a dictionary of template variables that should be provided at runtime.


.. literalinclude:: ../../examples/templated_lsig/sig_checker.py
    :lines: 22-25
    :emphasize-lines: 3


.. autoclass:: LogicSignature
    :members:

.. autoclass:: LogicSignatureTemplate
    :members:

.. autoclass:: RuntimeTemplateVariable
    :members:

.. _lsig_example:

Logic Signature Example
-----------------------

.. literalinclude:: ../../examples/templated_lsig/sig_checker.py