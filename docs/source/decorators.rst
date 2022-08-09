Decorators
===========

Beaker uses decorated methods to apply configurations to the methods they decorate.  The configuration allows the ``Application`` class to know how to expose them.


.. module:: beaker.decorators

.. _external:

ABI Method external
--------------------

The ``external`` decorator is how we can add methods to be handled as ABI methods. 

Tagging a method as ``external`` adds it to the internal ``Router`` with whatever configuration is passed, if any.

.. autodecorator:: external



.. _authorization:

Authorization
^^^^^^^^^^^^^

Often, we would like to restrict the accounts that may call certain methods. 

.. autoclass:: Authorize


Lets add a parameter to the external to allow only the app creator to call this method.

.. code-block:: python

    from beaker import Authorize

    #...

    @external(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter)
        )

The ``authorize`` parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  

The pre-defined Authorized checks are: 

.. automethod:: Authorize.only
.. automethod:: Authorize.holds_token
.. automethod:: Authorize.opted_in


But we can define our own

.. code-block:: python

    from beaker.consts import Algos

    @internal(TealType.uint64)
    def is_whale(acct: Expr):
        # Only allow accounts with 1mm algos
        return Balance(acct)>Algos(1_000_000)

    @external(authorize=is_whale)
    def greet(*, output: abi.String):
        return output.set("hello whale")



.. _method_hints:

Method Hints
^^^^^^^^^^^^

.. autoclass:: MethodHints
    :members:



.. _read_only:

**Read Only**

Methods that are meant to only produce information, having no side effects, should be flagged as read only. 

See `ARC22 <https://github.com/algorandfoundation/ARCs/pull/79>`_ for more details.

.. code-block:: python

    count = ApplicationStateValue(stack_type=TealType.uint64) 

    @external(read_only=True)
    def get_count(self, id_of_thing: abi.Uint8, *, output: abi.Uint64):
        return output.set(self.count)


.. _internal_methods:

Internal Methods
----------------

An Application will often need a number of internal ``utility`` type methods to handle common logic.  
We don't want to expose these methods to the ABI but we do want to allow them to access any instance variables.

.. note:: 
    If you want some method to return the expression only and not be triggered with ``callsub``, omit the ``@internal`` decorator and the expression will be inlined 


.. autodecorator:: internal

.. code-block:: python

    @internal(TealType.uint64)
    def do_logic(self):
        return If(self.counter>10, self.send_asset())



.. _bare_externals:

Bare externals
---------------

The ARC4 spec allows applications to define externals for ``bare`` methods, that is methods with no application arguments. 

Routing for ``bare`` methods is based on the transaction's ``OnComplete`` and whether or not it's a Create transaction.

Single Bare externals
^^^^^^^^^^^^^^^^^^^^^^

If a single OnComplete should be handled by a given method, use one of the pre-defined helpers.

.. autodecorator:: create
.. autodecorator:: delete 
.. autodecorator:: update 
.. autodecorator:: opt_in 
.. autodecorator:: close_out 
.. autodecorator:: clear_state 
    


Multiple Bare externals
^^^^^^^^^^^^^^^^^^^^^^^^

If a method requires handling multiple ``OnComplete`` actions, use ``bare_external``

.. autodecorator:: bare_external


.. _parameter_annotations:

Parameter Annotations
---------------------

.. autoclass:: ParameterAnnotation



A caller of our application should be provided with all the information they might need in order to make a successful application call.

One example of this of information is of course the parameter name and type. These bits of information are already provided by the normal method definition. 

 
.. _parameter_description:

Parameter Description
^^^^^^^^^^^^^^^^^^^^^^

Another example that is harder to provide is the description of the parameter. The plain english explanation of what the parameter _should_ be can be quite helpful in determining what to pass the method. To set a description on a parameter you can use the python ``typing.Annotated`` generic class and pass it an instance of ``ParameterAnnotation``.

.. code-block:: python

    from typing import Annotated

    #...

    @external
    def unhelpful_method_name(self, num: Annotated[
        abi.Uint64, 
        ParameterAnnotation(
            descr="The magic number, which should be prime, else fail"
        )
    ]):
        return is_prime(num.get())


Here we've annotated the ``num`` parameter with a description that should help the caller figure out what should be passed. This description is added to the appropriate method args description field in the json spec.


.. _parameter_default:

Parameter Default Value
^^^^^^^^^^^^^^^^^^^^^^^

In the ``OpUp`` example the argument ``opup_app`` should be the id of the application that we use to increase our budget via inner app calls.  This value should not change frequently, if at all, but is still required to be passed by the caller so we may _use_ it in our logic. 

Using the ``default`` field of the ``ParameterAnnotation``, we can specify a default value for the parameter.  This allows the caller to know this pseudo-magic number ahead of time and makes calling your application easier.

We can change the method signature of the ``hash_it`` function to something like:

.. code-block:: python

    @external
    def hash_it(
        self,
        input: Annotated[abi.String, ParameterAnnotation(descr="The input to hash")],
        iters: Annotated[
            abi.Uint64, ParameterAnnotation(descr="The number of times to iterate")
        ],
        opup_app: Annotated[
            abi.Application,
            ParameterAnnotation(
                descr="The app id to use for opup reququests",
                default=OpUp.opup_app_id,
            ),
        ],
        *,
        output: Annotated[
            abi.StaticArray[abi.Byte, Literal[32]],
            ParameterAnnotation(
                descr="The result of hashing the input a number of times"
            ),
        ],
    ):



The ``opup_app`` parameter now has a default value, the value stored at the ApplicationStateValue of ``opup_app_id``.  This information is communicated through the full ApplicationSpec as a hint the caller can use to figure out what the value should be.

Options for default arguments are:

- A constant, `Bytes | Int`
- State Values, `ApplicationStateValue | AccountStateValue`
- A read-only ABI method  

The result is that we can call the method, omitting the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the `ApplicationClient` consults the method definition to check that all the expected arguments are passed. If it finds one missing, it will check for hints for the method that may be resolvable. Upon finding a resolvable it will look up the state value, call the method, or return the constant value. The resolved value is passed in for argument.
