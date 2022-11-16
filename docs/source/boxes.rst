Boxes
=====

.. currentmodule:: beaker.lib.storage

Applications that need to maintain a large amount of state can use ``Box`` data storage.

:ref:`Full Example <box_example>`

While ``PyTeal`` provides the basic tools for working with boxes, ``Beaker`` provides a few handy abstractions for working with them.

.. _mapping:


Mapping
--------

A ``Mapping`` provides a way to store data with a given key. 

.. warning::
    Care should be taken to ensure if multiple ``Mapping`` types are used, there is no overlap with keys. If there may be overlap, a ``prefix`` argument *MUST* be set in order to provide a unique namespace. 

.. autoclass:: Mapping
    :members:

.. autoclass:: MapElement
    :members:

.. _listing:

List
----

A List provides a way to store some number of some _static_ abi type. 

.. note::
    Since the ``List`` uses the size of the element to compute the offset into the box, the data type *MUST* be static.

.. autoclass:: List
    :members:

.. autoclass:: ListElement
    :members:


.. _box_example:

Full Example
------------

.. literalinclude:: ../../examples/boxen/application.py

