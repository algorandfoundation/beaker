1.0 Migration Guide
===================

The following guide illustrates the changes in applications written with ``0.x`` version of Beaker compared to ``1.0``

Application instantiation
-------------------------

With version ``1.0`` of Beaker an application is no longer defined by inheriting ``Application``, instead
``Application`` is instantiated directly, state is separated from the class, and methods are
add through decorators on the ``Application`` instance.

For example in ``0.x``:

.. code-block:: python

   class MyApp(beaker.Application):
        my_value = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def set_value(self, new_value: pyteal.abi.Uint64) -> pyteal.Expr:
            return self.my_value.set(new_value.get())

   app = MyApp()

in ``1.0`` this becomes:

.. code-block:: python

    class MyState:
        my_value = beaker.ApplicationStateValue(pyteal.TealType.uint64)

    app = beaker.Application("MyApp", state=MyState())

    @app.external
    def set_value(new_value: pyteal.abi.Uint64) -> pyteal.Expr:
        return app.state.my_value.set(new_value.get())


The key changes to note above:

1. There is no subclassing, instead a ``beaker.Application`` instance is created.
2. Application and account state remain in a class, an instance of which is passed to ``beaker.Application(state=...)``.
   This is then accessible through the ``.state`` property on the ``Application`` instance.

    .. note:: There are additional ways to organize state in ``1.0``, but the above is the most straight forward conversion.

3. Method decorators exist on the ``Application`` instance, rather than being in the ``beaker`` namespace.
4. There is no longer a ``self`` parameter in ``my_method``. The method belongs to this specific ``app`` instance, rather than
   belonging to any class.

.. note:: In the following examples, we will continue to assign the app instance to a variable named ``app``,
          but you can call that variable whatever you want, for example:

.. code-block:: python

    awesome_app = beaker.Application("Awesome")

    @awesome_app.external
    def say_hello(*, output: pyteal.abi.String) -> pyteal.Expr:
        return output.set(pyteal.Bytes("Hello I'm Awesome"))


Application() arguments
-----------------------

.. code-block:: python

    class MyApp(beaker.Application):
        """This is my Beaker app. There are others like it, but this one is mine"""
        ...

    app = MyApp(
        version=7,
        optimize_options=pyteal.OptimizeOptions(scratch_slots=False, frame_pointers=False),
    )

in ``1.0`` this becomes:

.. code-block:: python

    app = beaker.Application(
        "MyApp",
        build_options=beaker.BuildOptions(avm_version=7, scratch_slots=False, frame_pointers=False),
        descr="This is my Beaker app. There are others like it, but this one is mine",
    )

Key changes:

1. The first parameter to ``Application()`` is the name of the app. This was taken from the name of the class in 0.x, so
   the above examples should be equivalent.
2. All options that control TEAL generation are under ``build_options``, and ``version`` has been renamed to ``avm_version``.
3. The ``desc`` field in the ARC-4 contract was taken from the doc-string of the class in 0.x (or a base class if no
   doc-string was defined), this is now the ``descr`` parameter.

Application.id and Application.address
----

``Application.id`` and ``Application.address`` have been removed. These shortcuts were potentially misleading for
new developers - they always return the ID and Address of the currently executing application, not the application
which they were accessed through. In the case of multiple applications in a single code base, this could be misleading.

To migrate:

1. Replace usages of ``self.address`` with ``Global.current_application_address()``.
2. Replace usages of ``self.id`` with ``Global.current_application_id()``.

Decorators
----------

The following decorators are all now accessed through the ``Application`` instance, rather than from ``beaker``.

* ``@beaker.external``
* ``@beaker.create``
* ``@beaker.delete``
* ``@beaker.update``
* ``@beaker.close_out``
* ``@beaker.no_op``
* ``@beaker.clear_state``

.. note:: There were recent changes in PyTeal to the way ``ClearState`` is handled, which were incorporated in beaker v0.5.1.
  In particular, ``ClearState`` handler methods must now take no arguments. Previously, this was considered valid PyTeal,
  however since the clear state program can not reject, there is no way to ensure these arguments are available, leading
  to silent failures.

TODO: deocrated methods return ABIReturnSubroutine or SubroutineWrapperFn now, not the original method - it's unlikely
people were using this according to Ben, but we should note that these will no longer be inlined.

internal
^^^^^^^^

The ``beaker.internal`` decorator is no longer required and has been removed. It can be replaced with one of the following

+--------------------------+--------------------------------------+-----------------------------+
|``0.x`` internal          |Equivalent ``1.0`` decorator          |Notes                        |
+==========================+======================================+=============================+
|``@internal(TealType.*)`` |``@pyteal.Subroutine(TealType.*)``    |Creates a subroutine         |
+--------------------------+--------------------------------------+-----------------------------+
|``@internal``             |None                                  |Expression will be inlined,  |
+--------------------------+                                      |matching previous behaviour. |
|``@internal(None)``       |                                      |                             |
+--------------------------+--------------------------------------+-----------------------------+
|``@internal``             |``@pyteal.ABIReturnSubroutine``       |Creates an ABI subroutine,   |
+--------------------------+                                      |matching expected behaviour. |
|``@internal(None)``       |                                      |                             |
+--------------------------+--------------------------------------+-----------------------------+


.. note:: Due to a bug in ``0.x`` beaker, ``@internal`` decorators without a ``TealType`` were always inlined.

For example in ``0.x``:

.. code-block:: python

    class MyApp(beaker.Application):

        @beaker.internal(TealType.uint64)
        def add(self, a: pyteal.Expr, b: pyteal.Expr) -> pyteal.Expr:
            return a + b

in ``1.0`` this becomes:

.. code-block:: python

    @pyteal.Subroutine(TealType.uint64)
    def add(a: pyteal.Expr, b: pyteal.Expr) -> pyteal.Expr:
        return a + b

bare_external
^^^^^^^^^^^^^

The ``beaker.bare_external`` decorator has been removed, instead an equivalent decorator on an ``Application``
instance can be used.

====================================================== ======================================
``0.x`` bare_external                                  Equivalent ``1.0`` decorator
====================================================== ======================================
``@bare_external(no_op=CallConfig.CALL)``              ``@app.no_op`` or ``@app.external(bare=True)``
``@bare_external(opt_in=CallConfig.CALL)``             ``@app.opt_in``
``@bare_external(delete_application=CallConfig.CALL)`` ``@app.delete``
``@bare_external(update_application=CallConfig.CALL)`` ``@app.update``
``@bare_external(close_out=CallConfig.CALL)``          ``@app.close_out``
``@bare_external(clear_state=CallConfig.CALL)``        ``@app.clear_state``
====================================================== ======================================

Depending on the bare_external configuration specified, additional arguments may be required

====================== =======================================
``CallConfig`` value   Additional arguments in ``1.0``
====================== =======================================
``CallConfig.CALL``    None
``CallConfig.CREATE``  ``allow_call=False, allow_create=True``
``CallConfig.ALL``     ``allow_create=True``
====================== =======================================

.. note:: The ``no_op``, ``opt_in``, ``delete``, ``update`` and ``close_out`` decorators can also be expressed as
          more general ``external`` decorators
          e.g. ``@app.opt_in(bare=True)`` is equivalent to ``@app.external(bare=True, method_config={"opt_int": CallConfig.CALL})``

2. If multiple actions are specified, then ``@app.external(bare=True, method_config={..})`` can be used.

For example in ``0.x``:

.. code-block:: python

   class MyApp(Application):
        @beaker.bare_external(no_op=pyteal.CallConfig.CALL, update_application=pyteal.CallConfig.CALL)
        def my_method(self):
            ...


in ``1.0`` this becomes:

.. code-block:: python

   app = beaker.Application("MyApp")

   @app.external(bare=True, method_config={"no_op": pyteal.CallConfig.CALL, "update_application": pyteal.CallConfig.CALL})
   def my_method():
        ...


Blueprints
----------

In beaker ``0.x`` applications were composed via inheritance and functionality could be shared via base classes.
In beaker ``1.0`` the concept of blueprints has been introduced, blueprints are used to add functionality to an app
instance.

For example in ``0.x``:

.. code-block:: python

    class Calculator(beaker.Application):

        @beaker.external
        def add(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64):
            output.set(a.get() + b.get())

    # to use Calculator, MyApp inherits Calculator
    class MyApp(Calculator)
        ...

In ``1.0`` the base class becomes a blueprint:

.. code-block:: python

    def calculator_blueprint(app: beaker.Application) -> None:

        @app.external
        def add(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64):
            ...

Or alternatively: (TODO: is this correct/recommended?)

.. code-block:: python

    def add(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64):
        ...

    def calculator_blueprint(app: Application) -> None:
        app.external(add)

The blueprint can then be added to an application using ``app.implement``:

.. code-block:: python

    app = beaker.Application("MyApp")
    app.implement(calculator_blueprint)


Overrides
---------

In beaker ``0.x`` because applications were composed by inheritance it was possible to override a method by redefining
it in the derived class. In ``1.0`` this instead can be achieved by removing the old reference from the app and adding a new one.

An example involving replacing a method with the same signature and replacing a method with a different signature

In ``0.x`` when overriding a method with a new implementation with the same signature

.. code-block:: python

    class BaseApp(beaker.Application):

        @beaker.external
        def same_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

    class DerivedApp(BaseApp):

        @beaker.external
        def same_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

in ``1.0``

.. code-block:: python

    def base_app(app: beaker.Application) -> None:
        @app.external
        def same_signature(a: abi.Uint64, b: abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").implement(base_app)

    @app.external(override=True)
    def same_signature(a: abi.Uint64, b: abi.Uint64):
        ...

In ``0.x`` when overriding a method with a new method with a different signature

.. code-block:: python

    class BaseApp(beaker.Application):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

    class DerivedApp(beaker.BaseApp):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, c: pyteal.abi.Uint64):
            ...

in ``1.0``

.. code-block:: python

    def base_app(app: beaker.Application) -> None:
        @app.external
        def different_signature(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").implement(base_app)

    # remove method defined by a blueprint
    app.deregister_abi_method("different_signature")

    # add our new method
    @app.external
    def different_signature(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, c: pyteal.abi.Uint64):
        ...


Logic signatures
----------------

With version ``1.0`` a logic signature is no longer defined by inheriting ``beaker.LogicSignature``, instead
``LogicSignature`` is instantiated directly, and the PyTeal expression is passed as an argument.

For example in ``0.x``:

.. code-block:: python

    class MySignature(beaker.LogicSignature):
        def evaluate(self) -> pyteal.Expr:
            return pyteal.Approve()

    my_signature = MySignature()

in ``1.0`` this becomes:

.. code-block:: python

    def evaluate() -> pyteal.Expr:
        return pyteal.Approve()

    my_signature = beaker.LogicSignature(evaluate)

The key changes to note above:

1. There is no subclassing, instead a ``beaker.LogicSignature`` instance is created.
2. A function returning a PyTeal expression (or more simply just a PyTeal expression) is passed to ``LogicSignature``
   instead of implementing ``def evaluate(self)``

Templated Logic signatures
^^^^^^^^^^^^^^^^^^^^^^^^^^

**TODO**

Precompiled
-----------

In ``0.x`` logic signatures and applications could be precompiled by adding an ``AppPrecompile`` or
``LSigPrecompile`` attribute to the application class and then it is available for use inside
the applications PyTeal expressions.

In ``1.0`` this approach has changed to using the ``beaker.precompiled`` function.

For example in ``0.x``:

.. code-block:: python

    class MyLogicSignature(beaker.LogicSignature):
        def evaluate(self):
            return pyteal.Approve()

    class MyApp(Application)
        precompile = LSigPrecompile(MyLogicSignature())

        @beaker.external
        def check_it(self):
            return pyteal.Assert(pyteal.Txn.sender() == self.precompile.logic.hash())

In ``1.0`` this becomes:

.. code-block:: python

    my_logic_signature = beaker.LogicSignature(pyteal.Approve())

    app = beaker.Application("MyApp")

    @app.external
    def check_it(self):
        precompiled = beaker.precompiled(my_logic_signature)
        return pyteal.Assert(pyteal.Txn.sender() == precompile.address())

TODO: logic.hash() -> address() + others

Library functions
-----------------

The ``beaker.lib`` functions used to create PyTeal expressions were renamed from ``snake_case`` style names
to ``PascalCase`` style names so they were consistent with PyTeal's convention of using ``PascalCase`` for code
that produces TEAL. The following is a list of functions affected.

=================== =================
``0.x`` Name        ``1.0`` Name
=================== =================
``iterate``         ``Iterate``
``even``            ``Even``
``odd``             ``Odd``
``saturate``        ``Saturate``
``min``             ``Min``
``max``             ``Max``
``div_ceil``        ``DivCeil``
``pow10``           ``Pow10``
``wide_power``      ``WidePower``
``factorial``       ``Factorial``
``exponential``     ``Exponential``
``wide_factorial``  ``WideFactorial``
``atoi``            ``Atoi``
``itoa``            ``Itoa``
``witoa``           ``Witoa``
``head``            ``Head``
``tail``            ``Tail``
``prefix``          ``Prefix``
``suffix``          ``Suffix``
``rest``            ``Rest``
``encode_uvarint``  ``EncodeUVarInt``
=================== =================

Import paths
^^^^^^^^^^^^

A number of internal modules in ``beaker.lib`` were removed. The following is a list of affected modules,
their contents can now be found directly under ``beaker.lib``

* ``beaker.lib.inline.inline_asm``
* ``beaker.lib.iter.iter``
* ``beaker.lib.math.math``
* ``beaker.lib.strings.string``


Compile
-------

``Application.compile`` has been renamed to ``build()`` and now returns an ``ApplicationSpecification`` which can be
serialized and deserialized using ``to_json()`` and ``from_json()`` respectively.

This allows building an ``Application``, serializing the specification to disk, and then deserializing the
specification later, which can then be used with ``ApplicationClient``


.. code-block:: python
    from beaker import Application, ApplicationClient
    from beaker.sandbox import get_algod_client

    app = Application("MyApp")
    #define application
    ...

    specification = app.build()
    client = ApplicationClient(get_algod_client(), specification)

