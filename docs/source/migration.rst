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
3. The ``desc`` field in the ARC-4 contract was taken from the doc-string of the class in ``0.x`` (or a base class if no
   doc-string was defined), this is now the ``descr`` parameter.

Application.id and Application.address
--------------------------------------

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

The ``beaker.bare_external`` decorator has been removed, but can be replaced with ``Application.external``
by moving the parameters to ``method_config`` and adding ``bare=True``.

For example in ``0.x``:

.. code-block:: python

    class MyApp(beaker.Application):

        @beaker.bare_external(opt_in=CallConfig.CREATE, no_op=CallConfig.CREATE)
        def foo(self):
            ...

In ``1.0`` this becomes:

.. code-block:: python

    app = beaker.Application("MyApp")

    @app.external(bare=True,
        method_config=pyteal.MethodConfig(opt_in=CallConfig.CREATE, no_op=CallConfig.CREATE))
    def foo():
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

For example in ``0.x`` an override with the same signature:

.. code-block:: python

    class BaseApp(beaker.Application):

        @beaker.external
        def same_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

    class DerivedApp(BaseApp):

        @beaker.external
        def same_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

In ``1.0`` this becomes:

.. code-block:: python

    def base_app(app: beaker.Application) -> None:
        @app.external
        def same_signature(a: abi.Uint64, b: abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").implement(base_app)

    @app.external(override=True)
    def same_signature(a: abi.Uint64, b: abi.Uint64):
        ...

For example in ``0.x`` an override with a different signature:

.. code-block:: python

    class BaseApp(beaker.Application):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...

    class DerivedApp(beaker.BaseApp):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, c: pyteal.abi.Uint64):
            ...

In ``1.0`` this becomes:

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

With version ``1.0`` a template logic signature is no longer defined by inheriting ``beaker.LogicSignature``, instead
``LogicSignatureTemplate`` is instantiated directly, and the PyTeal expression and a dictionary of template variables
are passed as arguments.

For example in ``0.x``:

.. code-block:: python

    class MySignature(beaker.LogicSignature):

        some_value = beaker.TemplateVariable(pyteal.TealType.uint64)

        def evaluate(self):
            return self.some_value

    my_signature = MySignature()

in ``1.0`` this becomes:

.. code-block:: python

    def evaluate(some_value: pyteal.Expr):
        return some_value

    my_signature = beaker.LogicSignatureTemplate(
        evaluate,
        runtime_template_variables={"some_value": pyteal.TealType.uint64},
    )

The key changes to note are:

1. There is no subclassing, instead a ``beaker.LogicSignatureTemplate`` instance is created
2. A function returning a PyTeal expression is passed to ``LogicSignatureTemplate`` instead of implementing ``def evaluate(self)``
3. A dictionary of template variable name and types is passed instead of instantiating ``beaker.TemplateVariable``
   for each variable.
4. The template variables are provided as arguments to the evaluation function

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

The following properties have been moved

+--------------------------------------+--------------------------------------+---------------------------------+
|Type of precompile                    |``0.x``                               |``1.0``                          |
+======================================+======================================+=================================+
|``PrecompiledApplication``            |``approval.program_pages[i].binary``  |``approval_program.pages[i]``    |
|                                      +--------------------------------------+---------------------------------+
|                                      |``approval.hash``                     |``approval_program.binary_hash`` |
|                                      +--------------------------------------+---------------------------------+
|                                      |``clear.program_pages[i].binary``     |``clear_program.pages[i]``       |
|                                      +--------------------------------------+---------------------------------+
|                                      |``clear.hash``                        |``clear_program.binary_hash``    |
+--------------------------------------+--------------------------------------+---------------------------------+
| ``PrecompiledLogicSignature``        |``logic``                             |``logic_program``                |
| ``PrecompiledLogicSignatureTemplate``+--------------------------------------+---------------------------------+
|                                      |``logic.hash``                        |``address``                      |
+--------------------------------------+--------------------------------------+---------------------------------+

.. note:: Properties for the source ``Application`` or ``LogicSignature`` have been removed.
          ``PrecompiledApplication`` still has the ``get_create_config()`` method for use when creating precompiled
          applications. ``PrecompiledLogicSignature`` and ``PrecompiledLogicSignatureTemplate`` have the ``address``
          property for obtaining a Logic Signatures address.

Signer
^^^^^^

In ``0.x`` the signer for logic signatures was on the precompiled reference. In ``1.0`` this has been removed,
so to obtain the signer for use in the ``ApplicationClient`` the signer needs to be created.

For example in ``0.x``:

.. code-block:: python

    class MySignature(beaker.LogicSignature):
        ...
    signature = MySignature()

    class MyApp(beaker.Application)
        precompiled_signature = beaker.LSigPrecompile(signature)
        ...


    account = sandbox.get_accounts().pop()
    app = MyApp()
    app_client = beaker.client.ApplicationClient(beaker.sandbox.get_algod_client(), app, signer=account.signer)
    app_client.create()

    signature_signer = app.precompiled_signature.template_signer(algosdk.encoding.decode_address(account.address))
    signature_client = app_client.prepare(signer=signature_signer)

In ``1.0`` this becomes:

.. code-block:: python

    signature = beaker.LogicSignatureTemplate(...)
    app = beaker.Application("App")

    @app.external
    def foo():
        precompiled_signature = beaker.precompile(my_signature)
        ...

    account = sandbox.get_accounts().pop()
    app_client = beaker.client.ApplicationClient(beaker.sandbox.get_algod_client(), app, signer=account.signer)
    app_client.create()

    precompiled_signature = beaker.PrecompiledLogicSignatureTemplate(signature, app_client.client)
    signature_signer = beaker.LogicSigTransactionSigner(
        algosdk.transaction.LogicSigAccount(
            precompiled_signature.populate_template(user_addr=decode_address(account.address))
        )
    )
    signature_client = app_client.prepare(signer=signature_signer)


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

