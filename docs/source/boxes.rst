Boxes
=====

.. currentmodule:: beaker.lib.storage

Applications that need to maintain a large amount of state can use ``Box`` data storage.

:ref:`Full Example <box_example>`

While ``PyTeal`` provides the basic tools for working with boxes, ``Beaker`` provides a few handy abstractions for working with them.

.. _mapping:


BoxMapping
----------

A ``BoxMapping`` provides a way to store data with a given key. 

.. warning::
    Care should be taken to ensure if multiple ``BoxMapping`` types are used, there is no overlap with keys. If there may be overlap, a ``prefix`` argument *MUST* be set in order to provide a unique namespace. 

.. autoclass:: BoxMapping
    :members:

.. _listing:

BoxList
-------

A ``BoxList`` provides a way to store some number of some _static_ abi type. 

.. note::
    Since the ``BoxList`` uses the size of the element to compute the offset into the box, the data type *MUST* be static.

.. autoclass:: BoxList
    :members:

.. _box_example:

Full Example
------------

.. literalinclude:: ../../examples/boxen/application.py

