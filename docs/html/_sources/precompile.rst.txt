Precompile
==========

A Precompile as an attribute on a Beaker Application allows the contract to 
have some program be included in the source of the applications programs.

An example of where it might be used is in offloading some compute into a LogicSignature
which has a max budget of 20k ops compared with 700 ops in a single Application call. 

.. module:: beaker.precompile 

.. autoclass:: Precompile
    :members:

.. autoclass:: PrecompileTemplateValue
    :members: