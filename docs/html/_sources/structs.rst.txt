Structs
=======

.. module:: beaker.struct

With Beaker we can define a custom structure and use it in our ABI methods.

.. autoclass:: Struct

    .. automethod:: set
    .. automethod:: annotation_type

    .. automethod:: client_encode
    .. automethod:: client_decode


Example 
--------

.. literalinclude:: ../../examples/structure/main.py
    :lines: 16-57


The application exposes the ABI methods using the tuple encoded version of the fields specified in the struct. Here it would be ``(string,uint32)``.

A method hint is available to the caller for encoding/decoding by field name. 

To pass a struct we can pass a python dict ``dict``

.. literalinclude:: ../../examples/structure/main.py
    :lines: 77-80

And we can decode it from the tuple we get back

.. literalinclude:: ../../examples/structure/main.py
    :lines: 90-92
