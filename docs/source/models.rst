Models
=======

.. module:: beaker.model

With Beaker we can define a custom structure and use it in our ABI methods.

.. autoclass:: Model

    .. automethod:: set
    .. automethod:: annotation_type

    .. automethod:: client_encode
    .. automethod:: client_decode


Example 
--------

.. literalinclude:: ../../examples/model/model.py
    :lines: 18-54


The application exposes the ABI methods using the tuple encoded version of the fields specified in the model. Here it would be ``(string,uint32)``.

A method hint is available to the caller for encoding/decoding by field name. 

To pass a model we can pass a python dict ``dict``

.. literalinclude:: ../../examples/model/model.py
    :lines: 73-76

And we can decode it from the tuple we get back

.. literalinclude:: ../../examples/model/model.py
    :lines: 86-88
