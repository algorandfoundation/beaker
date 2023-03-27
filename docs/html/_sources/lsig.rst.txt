Logic Signatures
================

.. module:: beaker.logic_signature

A ``LogicSignature`` (or ``Smart Signature``) acts as a signature that is verified by a smart contract instead of a public key see `Algorand docs <https://developer.algorand.org/docs/>`_ for more information. 

A Beaker ``LogicSignature`` is initialized with either a PyTeal ``Expr`` or a function that returns an ``Expr``.

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