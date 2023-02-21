1.0 Migration Guide
===================

The following guide illustrates the changes in applications written with ``0.x`` version of Beaker compared to ``1.0``

Application
-----------

Application instantiation
^^^^^^^^^^^^^^^^^^^^^^^^^

With version ``1.0`` of Beaker an application is no longer defined by inheriting ``Application``, instead
``Application`` is instantiated directly, state is separated from the class, and methods are
added through decorators on the ``Application`` instance.

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
^^^^^^^^^^^^^^^^^^^^^^^

The arguments that ``Application.__init__()`` takes have changed, the following in ``0.5.4``:

.. code-block:: python

    class MyApp(beaker.Application):
        """This is my Beaker app. There are others like it, but this one is mine"""
        ...

    app = MyApp(
        version=7,
        optimize_options=pyteal.OptimizeOptions(scratch_slots=False, frame_pointers=False),
    )

becomes this in ``1.0``:

.. code-block:: python

    app = beaker.Application(
        "MyApp",
        build_options=beaker.BuildOptions(avm_version=7, scratch_slots=False, frame_pointers=False),
        descr="This is my Beaker app. There are others like it, but this one is mine",
    )

Key changes:

1. The first parameter to ``Application()`` is the name of the app. This was taken from the name of the class in ``0.x``,
   so the above examples should be equivalent.
2. All options that control TEAL generation are under ``build_options``, and ``version`` has been renamed to ``avm_version``.
3. The ``desc`` field in the ARC-4 contract was taken from the doc-string of the class in ``0.x`` (or a base class if no
   doc-string was defined), this is now the ``descr`` parameter.

Application.id and Application.address
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``Application.id`` and ``Application.address`` have been removed. These shortcuts were potentially misleading - they
always return the ID and Address of the currently executing application, not the application which they were accessed
through. In the case of multiple applications in a single code base, this could be misleading.

To migrate:

1. Replace usages of ``self.address`` with ``Global.current_application_address()``.
2. Replace usages of ``self.id`` with ``Global.current_application_id()``.


Application.compile()
^^^^^^^^^^^^^^^^^^^^^

``Application.compile()`` has been renamed to ``build()`` and now returns an ``ApplicationSpecification``, which contains,
among other things, the approval and clear program TEAL that was previously returned.

In ``0.x``:

.. code-block:: python

    app = MyApp()
    approval_program, clear_program = app.compile()
    app.dump("output_dir")

In ``1.0``:

.. code-block:: python

    app = beaker.Application("MyApp")
    app_spec = app.build()
    approval_program, clear_program = app_spec.approval_program, app_spec.clear_program
    app_spec.export("output_dir")


Importantly, this change allows building an ``Application``, serializing the specification to disk, and then deserializing the
specification later, which can then be used with ``ApplicationClient``.

.. code-block:: python

    app = beaker.Application("MyApp")
    app_spec = app.build()
    app_spec.export("output_dir")

    # later, potentially in another code-base, or running in CI/CD
    client = beaker.ApplicationClient(client=..., app="output_dir/application.json")

    # as a shortcut, if the ApplicationClient is in the same codebase as the Application:
    client = beaker.ApplicationClient(client=..., app=app)


.. note:: The result of ``beaker.Application().build(...)`` is not cached.

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

.. note:: There were recent changes in PyTeal to the way ``ClearState`` is handled, which were incorporated in Beaker v0.5.1.
  In particular, ``ClearState`` handler methods must now take no arguments. Previously, this was considered valid PyTeal,
  however since the clear state program can not reject, there is no way to ensure these arguments are available, leading
  to silent failures.

.. note:: Decorated methods now return ``ABIReturnSubroutine`` or ``SubroutineWrapperFn``, not the original method. This
          should mostly be an internal change only, but if these methods were being invoked by other methods within the
          contract, this will result in changes to TEAL output as they will no longer be inlined.

@internal
^^^^^^^^^

The ``beaker.internal`` decorator is no longer required and has been removed. It can be replaced with one of the following:

+--------------------------+--------------------------------------+--------------------------------+
|``0.x`` internal          |Equivalent ``1.0`` decorator          |Notes                           |
+==========================+======================================+================================+
|``@internal(TealType.*)`` |``@pyteal.Subroutine(TealType.*)``    |Creates a subroutine            |
+--------------------------+--------------------------------------+--------------------------------+
|``@internal``             |None                                  | | Expression will be inlined,  |
+--------------------------+                                      | | matching previous behaviour. |
|``@internal(None)``       |                                      |                                |
+--------------------------+--------------------------------------+--------------------------------+
|``@internal``             |``@pyteal.ABIReturnSubroutine``       | | Creates an ABI subroutine,   |
+--------------------------+                                      | | matching expected behaviour. |
|``@internal(None)``       |                                      |                                |
+--------------------------+--------------------------------------+--------------------------------+

.. note:: Due to a bug in ``0.x`` Beaker, ``@internal`` decorators without a ``TealType`` were always inlined.

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

@bare_external
^^^^^^^^^^^^^^

The functionality of ``beaker.bare_external`` decorator have been incorporated into ``@external``.
``@beaker.bare_external`` in ``0.x`` can be replaced with ``Application.external`` by moving the parameters to
``method_config`` and adding ``bare=True``.

For example in ``0.x``:

.. code-block:: python

    class MyApp(beaker.Application):
        @beaker.bare_external(
            opt_in=pyteal.CallConfig.CREATE,
            no_op=pyteal.CallConfig.CREATE,
        )
        def foo(self) -> pyteal.Expr:
            ...

In ``1.0`` this becomes:

.. code-block:: python

    app = beaker.Application("MyApp")

    @app.external(
        bare=True,
        method_config=pyteal.MethodConfig(
            opt_in=pyteal.CallConfig.CREATE,
            no_op=pyteal.CallConfig.CREATE,
        ),
    )
    def foo() -> pyteal.Expr:
        ...

Sharing code or config between contracts
----------------------------------------

In Beaker ``0.x`` applications were composed via inheritance and functionality could be shared via base classes.
In Beaker ``1.0`` code or configuration needs to be shared via other means. The following will describe some alternative
approaches.

Using inheritance for State classes (as a way of sharing a common structure) is fine and supported in ``1.0``.

Any class constants used in ``0.x`` can be moved to module level constants in ``1.0``.

Other usages of inheritance in ``0.x`` are often around sharing code between different smart contracts
i.e. ``BaseApp`` contains some common functions and ``DerivedApp1`` and ``DerivedApp2`` can use those functions.
In these cases, the shared function can just be regular Python functions that each app calls as required

For example in ``0.x``:

.. code-block:: python

    class BaseApp(beaker.Application):
        ZERO = Int(0)

        base_state = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        def add(self, a: pyteal.Uint64, b: pyteal.Uint64) -> pyteal.Expr:
            return a + b

    class DerivedApp1(BaseApp):
        state1 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def add_1(self, a: pyteal.Uint64) -> Expr:
            return self.add(a, pyteal.Int(1))

    app1 = DerivedApp1()

    class DerivedApp2(BaseApp):
        state2 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def add_2(self, a: pyteal.Uint64) -> Expr:
            return self.add(a, pyteal.Int(2))

    app2 = DerivedApp2()

In ``1.0`` this could be:

.. code-block:: python

    ZERO = Int(0)

    class BaseState:
        base_state = beaker.ApplicationStateValue(pyteal.TealType.uint64)

    class App1State(BaseState):
        state1 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

    class App2State(BaseState):
        state2 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

    def add(a: pyteal.Uint64, b: pyteal.Uint64) -> pyteal.Expr:
        return a + b

    app1 = Application("DerivedApp1", state=App1State())

    @app1.external
    def add1(a: pyteal.Uint64):
        return add(a, pyteal.Int(1))

    app2 = Application("DerivedApp2", state=App2State())

    @app2.external
    def add2(a: pyteal.Uint64):
        return add(a, pyteal.Int(2))

There will be some scenarios where the above will not be sufficient, for example having the same ABI method across
multiple apps.

For these cases, the use of closure functions should be considered. This pattern is referred to in Beaker as "blueprints",
but these are nothing more than Python functions which take an ``Application`` instance, and possibly some arguments, and
modify the ``Application`` by adding methods to it.

For example, suppose two applications both need an ABI method that adds two numbers together named ``add``.

.. code-block:: python

    def calculator_blueprint(app: beaker.Application, fudge_factor: int = 0) -> None:

        @app.external
        def add(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64):
            return output.set(a.get() + b.get() + Int(fudge_factor))

The blueprint can then be applied to the applications using the shortcut ``app.implement``:

.. code-block:: python

    app = Application("App").implement(calculator_blueprint)

    off_by_one_app = Application("OffByOne").implement(calculator_blueprint, fudge_factor=1)


Note that this is equivalent to:

.. code-block:: python

    app = Application("App")
    calculator_blueprint(app)

    off_by_one_app = Application("OffByOne")
    calculator_blueprint(off_by_one_app, fudge_factor=1)


Overrides
---------

In Beaker ``0.x`` because applications were composed by inheritance it was possible to override a method by redefining
it in the derived class. In ``1.0`` this instead can be achieved by removing the old reference from the app and adding a new one.

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

    # this example uses the previously described blueprint pattern,
    # since generally the only scenario where overriding is needed
    # is when using code that is not part of the current code base.

    def a_blueprint(app: beaker.Application) -> None:
        @app.external
        def same_signature(a: abi.Uint64, b: abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").implement(a_blueprint)

    @app.external(override=True)
    def same_signature(a: abi.Uint64, b: abi.Uint64):
        ...

For example in ``0.x`` an override with a different signature:

.. code-block:: python

    class BaseApp(beaker.Application):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint64):
            ...

    class DerivedApp(beaker.BaseApp):

        @beaker.external
        def different_signature(self, a: pyteal.abi.Uint32, b: pyteal.abi.Uint32):
            ...

In ``1.0`` this becomes:

.. code-block:: python

    def a_blueprint(app: beaker.Application) -> None:
        @app.external(name="silly_walk")
        def different_signature(a: pyteal.abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").implement(a_blueprint)

    # remove method defined by a blueprint
    # note that we use the name of the Python function here
    app.deregister_abi_method("different_signature")

    # add our new method
    @app.external(name="silly_walk")
    def different_signature(a: pyteal.abi.Uint32, b: pyteal.abi.Uint32):
        ...

In the case of overriding a bare method to replace it with an ABI method:

.. code-block:: python

    def a_blueprint(app: beaker.Application) -> None:
        @app.no_op(name="something_completely_different")
        def different_signature():
            ...

    app = beaker.Application("DerivedApp").implement(a_blueprint)

    # remove method defined by a blueprint
    # note that we use the name of the Python function here
    app.deregister_bare_method("different_signature")

    # add our new method
    @app.external(name="something_completely_different")
    def different_signature(x: pyteal.abi.Uint32):
        ...


Logic signatures
----------------

With version ``1.0`` a logic signature is no longer defined by inheriting ``beaker.LogicSignature``, instead
``LogicSignature`` is instantiated directly, and the PyTeal expression - or a function returning an expression - is passed as an argument.

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

or equivalently:

.. code-block:: python

    my_signature = beaker.LogicSignature(pyteal.Approve())

The key changes to note above:

1. There is no subclassing, instead a ``beaker.LogicSignature`` instance is created.
2. A function returning a PyTeal expression (or perhaps more simply just a PyTeal expression) is passed to ``LogicSignature``
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
            return pyteal.ReturnValue(self.some_value)

    my_signature = MySignature()

in ``1.0`` this becomes:

.. code-block:: python

    def evaluate(some_value: pyteal.Expr):
        return pyteal.ReturnValue(some_value)

    my_signature = beaker.LogicSignatureTemplate(
        evaluate,
        runtime_template_variables={"some_value": pyteal.TealType.uint64},
    )

The key changes to note are:

1. There is no subclassing, instead a ``beaker.LogicSignatureTemplate`` instance is created.
2. A function returning a PyTeal expression (or just an expression) is passed to ``LogicSignatureTemplate``
   instead of implementing ``def evaluate(self)``.
3. A dictionary of template variable name and types is passed instead of instantiating ``beaker.TemplateVariable``
   for each variable.
4. The template variables are provided as arguments to the evaluation function. The function can omit these arguments
   if they are not used.

Precompiled
-----------

In ``0.x`` logic signatures and applications could be precompiled by adding an ``AppPrecompile`` or
``LSigPrecompile`` attribute to the application class, making certain properties available for use inside
the application's methods.

In ``1.0``, you do not need to reference any "precompile classes" directly, instead use the ``beaker.precompiled`` function.

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
    def check_it():
        precompile = beaker.precompiled(my_logic_signature)
        return pyteal.Assert(pyteal.Txn.sender() == precompile.address())

Note that ``beaker.precompiled(...)`` can only be used inside your applications methods. The application/logic signature will
only be compiled once for each app that references it.

In addition, the interface of precompiled logic signature objects has been simplified. As can be seen in the example above,
obtaining the address is done via ``.address()`` instead of ``.logic.hash()`` for normal logic signatures.

For templated logic signatures, this was previously ``.logic.template_hash(...)`` and the argument values were expected to be in the
correct order based on the order they were defined in the class. Now, you would use ``.address(...)`` but pass the values
by keyword only, for example:

.. code-block:: python

    class Lsig(beaker.LogicSignature):
         tv = beaker.TemplateVariable(pyteal.TealType.uint64)

         def evaluate(self):
             return pyteal.Seq(pyteal.Assert(self.tv), pyteal.Int(1))

     class App(Application):
         pc = beaker.LSigPrecompile(Lsig())

         @external
         def check_it(self):
             return pt.Assert(
                 pt.Txn.sender() == self.pc.logic.template_hash(pt.Int(tmpl_val))
             )

Could become:

.. code-block:: python

    lsig = LogicSignatureTemplate(
         lambda tv: pyteal.Seq(pyteal.Assert(tv), pyteal.Int(1)),
         runtime_template_variables={"tv": pyteal.TealType.uint64},
     )

    app = beaker.Application("App")

    @app.external
     def check_it() -> ptyeal.Expr:
         lsig_pc = beaker.precompiled(lsig)
         return pyteal.Assert(pyteal.Txn.sender() == lsig_pc.address(tv=pyteal.Int(tmpl_val)))

Note the ``tv=`` in the call to ``address``, versus the lack of the variable name in the call to ``template_hash`` previously.

As a side-effect, the order the variables are passed in to ``address()`` does not matter, as long as they are all specified.

Signer
^^^^^^

In ``0.x`` the signer for logic signatures was on the precompiled reference. In ``1.0`` this has been removed,
so to obtain the signer for use in the ``ApplicationClient`` the signer needs to be created.

For example in ``0.x``:

.. code-block:: python

    class MySignature(beaker.LogicSignature):
        ...

    class MyApp(beaker.Application)
        precompiled_signature = beaker.LSigPrecompile(MySignature())
        ...

    app.compile(client=...)

    signer = app.precompiled_signature.signer()

In ``1.0`` this becomes:

.. code-block:: python

    signature = beaker.LogicSignature(...)

    precompiled_signature = beaker.PrecompiledLogicSignature(signature, client=...)
    signer = algosdk.atomic_transaction_composer.LogicSigTransactionSigner(
        algosdk.transaction.LogicSigAccount(
            precompiled_signature.logic_program.raw_binary
        )
    )

Templated Signer
^^^^^^^^^^^^^^^^

In ``0.x``:

.. code-block:: python

    class MySignature(beaker.LogicSignature):
         tv = beaker.TemplateVariable(pyteal.TealType.uint64)
         ...

    class MyApp(beaker.Application)
        precompiled_signature = beaker.LSigPrecompile(MySignature())
        ...

    app.compile(client=...)

    signer = app.precompiled_signature.template_signer(123)

In ``1.0`` this becomes:

.. code-block:: python

    signature = beaker.LogicSignatureTemplate(
        lambda tv: ...,
        runtime_template_variables={"tv": pyteal.TealType.uint64}
    )

    precompiled_signature = beaker.PrecompiledLogicSignatureTemplate(signature, client=...)
    signer = algosdk.atomic_transaction_composer.LogicSigTransactionSigner(
        algosdk.transaction.LogicSigAccount(
            precompiled_signature.populate_template(tv=123)
        )
    )

State related classes and methods
---------------------------------

Version ``1.0`` of Beaker renamed existing state related to classes to follow the naming conventions
used more generally within existing Algorand and TEAL documentation. Generally the renames involved changing
``Application`` to ``Global`` and ``Account`` to ``Local``.

``beaker`` namespace changes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

=========================================== ==============================
``0.x`` Name                                ``1.0`` Name
=========================================== ==============================
``ApplicationStateValue``                   ``GlobalStateValue``
``AccountStateValue``                       ``LocalStateValue``
``ReservedApplicationStateValue``           ``ReservedGlobalStateValue``
``ReservedAccountStateValue``               ``ReservedLocalStateValue``
``ApplicationStateBlob``                    ``GlobalStateBlob``
``AccountStateBlob``                        ``LocalStateBlob``
=========================================== ==============================

``beaker.Application`` changes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

=================================== ============================
``0.x`` Name                        ``1.0`` Name
=================================== ============================
``initialize_application_state``    ``initialize_global_state``
``initialize_account_state``        ``initialize_local_state``
=================================== ============================

``beaker.client.ApplicationClient`` changes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

=========================== ======================
``0.x`` Name                ``1.0`` Name
=========================== ======================
``get_application_state``   ``get_global_state``
``get_account_state``       ``get_local_state``
=========================== ======================

``beaker.lib.storage`` changes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

=================== ======================
``0.x`` Name        ``1.0`` Name
=================== ======================
``List``            ``BoxList``
``ListElement``     ``BoxList.Element``
``Mapping``         ``BoxMapping``
``MapElement``      ``BoxMapping.Element``
=================== ======================


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

A number of internal modules in ``beaker.lib`` were collapsed. The following is a list of affected modules:

* ``beaker.lib.inline.inline_asm.*`` -> ``beaker.lib.inline.*``
* ``beaker.lib.iter.iter.*`` -> ``beaker.lib.iter.*``
* ``beaker.lib.math.math.*`` -> ``beaker.lib.math.*``
* ``beaker.lib.strings.string.*`` -> ``beaker.lib.string.*``




