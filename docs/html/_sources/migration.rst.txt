1.0 Migration Guide
===================

The following guide illustrates the changes in applications written with ``0.x`` version of Beaker compared to ``1.0``.
The rationale behind these changes is described by the `AlgoKit Beaker productionisation review architecture decision record <https://github.com/algorandfoundation/algokit-cli/blob/main/docs/architecture-decisions/2023-01-11_beaker_productionisation_review.md>`_.

The goal of these changes is to create a Beaker experience that is easier to use, less surprising and resolves some key bugs that were identified.

Recommended migration approach
------------------------------

Any migration effort requires careful consideration to ensure it doesn't result in breaking changes.
We have carefully articulated all considerations in this document that should be evaluated to perform a
successful migration of a ``0.x`` Beaker contract/signature to a ``1.0`` compatible one.

While there are a number of considerations to work through, care was taken to ensure that the migration
effort should be relatively straightforward. If you have any problems or questions about a migration feel
free to send messages to the `algokit channel in Algorand Discord <https://discord.com/channels/491256308461207573/1065320801970180168>`_.

In order to de-risk the migration effort we recommend you test for output stability of the TEAL code
that is generated from your Beaker code. This involves storing the current TEAL and application spec output from calling
``.dump()`` on your Beaker contract (now: ``.build().export()``) and then doing a diff after performing the migration. We expect there will be
minor re-ordering changes that PyTEAL generates, but outside of that the TEAL output should be the same and similarly there may
be some re-ordering and also some extra detail added to the application spec file.

You can `see an example here <https://gist.github.com/robdmoore/ffa1cd7aced58f788ef68ac497249ea6>`_ of such a diff as part of the migration
of the Beaker examples to ``1.0``.


Application
-----------

Application instantiation
^^^^^^^^^^^^^^^^^^^^^^^^^

With version ``1.0`` of Beaker an application is no longer defined by inheriting ``Application``, instead
``Application`` is instantiated directly, state is separated into its own class, and methods are
added through decorators on the ``Application`` instance.

.. note:: The examples in this guide are assumed to have the following imports at the top, but have been
          omitted for brevity ``import beaker`` and  ``import pyteal``

For example, in ``0.x``:

.. code-block:: python

   class MyApp(beaker.Application):
        my_value = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def set_value(self, new_value: pyteal.abi.Uint64) -> pyteal.Expr:
            return self.my_value.set(new_value.get())

   app = MyApp()

becomes the following in ``1.0``:

.. code-block:: python

    class MyState:
        my_value = beaker.GlobalStateValue(pyteal.TealType.uint64)


    app = beaker.Application("MyApp", state=MyState())


    @app.external
    def set_value(new_value: pyteal.abi.Uint64) -> pyteal.Expr:
        return app.state.my_value.set(new_value.get())

The key changes to note above:

1. There is no sub-classing, instead a ``beaker.Application`` instance is created (i.e. ``app = beaker.Application("MyApp", ...)``).
2. Application and account state remain in a class, an instance of which is passed to ``beaker.Application(state=...)``.
   This is then accessible through the ``.state`` property on the ``Application`` instance (e.g. ``app.state.my_value.set(...)``).

    .. note:: There are additional ways to organize state in ``1.0``, but the above is the most straight forward conversion.

3. Method decorators exist on the ``Application`` instance, rather than being in the ``beaker`` namespace (e.g. ``@app.external ...``).
4. There is no longer a ``self`` parameter needed when defining methods.

.. note:: In the following examples, we will continue to assign the app instance to a variable named ``app``,
          but you can call that variable whatever you want, for example:

.. code-block:: python

    awesome_app = beaker.Application("Awesome")

    @awesome_app.external
    def say_hello(*, output: pyteal.abi.String) -> pyteal.Expr:
        return output.set(pyteal.Bytes("Hello, I'm An Awesome App!"))


Application() arguments
^^^^^^^^^^^^^^^^^^^^^^^

The arguments that ``Application.__init__()`` takes have changed too. For instance, the following in ``0.5.4``:

.. code-block:: python

    class MyApp(beaker.Application):
        """This is my Beaker app. There are others like it, but this one is mine"""
        ...

    app = MyApp(
        version=7,
        optimize_options=pyteal.OptimizeOptions(scratch_slots=False, frame_pointers=False),
    )

Then becomes the following in ``1.0``:

.. code-block:: python

    app = beaker.Application(
        "MyApp",
        build_options=beaker.BuildOptions(
            avm_version=7, scratch_slots=False, frame_pointers=False
        ),
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

``Application.compile()`` has been renamed to ``build()``, which is a more accurate description of what happens at that step, and now returns an ``ApplicationSpecification``, which contains,
among other things, the approval and clear program TEAL that was previously returned.

This code in ``0.x``:

.. code-block:: python

    app = MyApp()
    approval_program, clear_program = app.compile()
    app.dump("output_dir")

Becomes this in ``1.0``:

.. code-block:: python

    app = beaker.Application("MyApp")
    app_spec = app.build()
    approval_program, clear_program = app_spec.approval_program, app_spec.clear_program
    app_spec.export("output_dir")

.. note:: The result of ``beaker.Application().build(...)`` is not cached.

Application Client
------------------

``ApplicationClient`` has been changed to no longer depend directly on an ``Application`` instance, this allows
building an ``Application``, serializing the specification to disk, and then deserializing the specification later
for use with ``ApplicationClient`` or a similar client in any other programming language. For example:

.. code-block:: python

    app = beaker.Application("MyApp")
    app_spec = app.build()
    app_spec.export("output_dir")

    # later, potentially in another code-base, or running in CI/CD
    client = beaker.client.ApplicationClient(client=..., app="output_dir/application.json")

    # as a shortcut, if the ApplicationClient is in the same codebase as the Application:
    client = beaker.client.ApplicationClient(client=..., app=app)

Due to the changes in how methods are defined, when using ``ApplicationClient.call`` the way methods are referenced
has changed.

For example, in ``0.x``:

.. code-block:: python

   class MyApp(beaker.Application):

        @beaker.external(name="foo")
        def do_something(self, x: pyteal.abi.Uint64) -> pyteal.Expr:
            ...

   app = MyApp()

   client = beaker.client.ApplicationClient(client=..., app=app)
   client.call(MyApp.do_something, x=42)

becomes the following in ``1.0``:

.. code-block:: python

    app = beaker.Application("MyApp")

    @app.external(name="foo")
    def do_something(x: pyteal.abi.Uint64) -> pyteal.Expr:
        ...

    app_spec = app.build()
    client = beaker.client.ApplicationClient(client=..., app=app_spec)

    # if in the same code base the method can be referenced directly OR,
    client.call(do_something, x=42)

    # the method can be referenced by contract name OR,
    client.call("foo", x=42)

    # the method can be referenced by method signature,
    # which is useful if there are overloaded signatures
    client.call("foo(uint64)", x=42)

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

Previously, all of these decorators except ``external`` would make a bare method (rather than an ABI method) if the
function they were decorating took no arguments (other than ``self``). In ``1.0``, bare methods must be requested
explicitly with ``bare=True``. To avoid making changes to existing contracts, you should add ``bare=True`` to any decorators
other than ``@external`` if and only if the function takes no arguments.

.. note:: There were recent changes in PyTeal to the way ``ClearState`` is handled, which were incorporated in Beaker v0.5.1.
  In particular, ``ClearState`` handler methods must now take no arguments. Previously, this was considered valid PyTeal,
  however since a clear state program reject will not prevent the accounts local state from being cleared,
  special care needs to be taken to allow as few conditions that might lead to rejection as possible.

Decorated methods now return ``ABIReturnSubroutine`` or ``SubroutineWrapperFn``, not the original method. This
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

    @pyteal.Subroutine(pyteal.TealType.uint64)
    def add(a: pyteal.Expr, b: pyteal.Expr) -> pyteal.Expr:
        return a + b

@bare_external
^^^^^^^^^^^^^^

The functionality of the ``beaker.bare_external`` decorator has been incorporated into ``@external``.
``@beaker.bare_external`` in ``0.x`` can be replaced with ``Application.external`` in ``1.0`` by moving the parameters to
``method_config`` and adding ``bare=True``.

For example, the following code in ``0.x``:

.. code-block:: python

    class MyApp(beaker.Application):
        @beaker.bare_external(
            opt_in=pyteal.CallConfig.CREATE,
            no_op=pyteal.CallConfig.CREATE,
        )
        def foo(self) -> pyteal.Expr:
            ...

Becomes this in ``1.0``:

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

        def add(self, a: pyteal.Expr, b: pyteal.Expr) -> pyteal.Expr:
            return a + b

    class DerivedApp1(BaseApp):
        state1 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def add_1(self, a: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64) -> Expr:
            return output.set(self.add(a.get(), pyteal.Int(1)))

    app1 = DerivedApp1()

    class DerivedApp2(BaseApp):
        state2 = beaker.ApplicationStateValue(pyteal.TealType.uint64)

        @beaker.external
        def add_2(self, a: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64) -> Expr:
            return output.set(self.add(a.get(), pyteal.Int(2)))

    app2 = DerivedApp2()

In ``1.0`` this could be:

.. code-block:: python

    ZERO = pyteal.Int(0)


    class BaseState:
        base_state = beaker.GlobalStateValue(pyteal.TealType.uint64)


    class App1State(BaseState):
        state1 = beaker.GlobalStateValue(pyteal.TealType.uint64)


    class App2State(BaseState):
        state2 = beaker.GlobalStateValue(pyteal.TealType.uint64)


    def add(a: pyteal.Expr, b: pyteal.Expr) -> pyteal.Expr:
        return a + b


    app1 = beaker.Application("DerivedApp1", state=App1State())


    @app1.external
    def add1(a: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64) -> pyteal.Expr:
        return output.set(add(a.get(), pyteal.Int(1)))


    app2 = beaker.Application("DerivedApp2", state=App2State())


    @app2.external
    def add2(a: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64) -> pyteal.Expr:
        return output.set(add(a.get(), pyteal.Int(2)))

There will be some scenarios where the above will not be sufficient, for example having the same ABI method across
multiple apps.

For these cases, you might want to instead add the same methods to multiple apps by writing a function to do so.

For example, suppose two applications both need an ABI method that adds two numbers together named ``add``.

.. code-block:: python

    def implement_addition(app: beaker.Application, free_bananas: int = 0) -> None:
        @app.external
        def add(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64, *, output: pyteal.abi.Uint64):
            return output.set(a.get() + b.get() + pyteal.Int(free_bananas))

The function can be applied to the applications using the shortcut ``app.apply``:

.. code-block:: python

    app = beaker.Application("App").apply(implement_addition)

    banana_app = beaker.Application("BananaApp").apply(implement_addition, free_bananas=1)

Note that this is exactly equivalent to:

.. code-block:: python

    app = beaker.Application("App")
    implement_addition(app)

    banana_app = beaker.Application("BananaApp")
    implement_addition(banana_app, free_bananas=1)


The main advantage to using the `.apply` method is that it can be chained together, since the result of `.apply` is always
the `Application` instance it was called on. You can use whichever method you find clearer or more convenient.

Overrides
---------

In Beaker ``0.x`` because applications were composed by inheritance it was possible to override a method by redefining
it in the derived class. In ``1.0`` this instead can be achieved by removing the old reference from the app and adding a new one.

For example in ``0.x`` an override with the same signature looks like this:

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

    # this example uses the previously described pattern of adding
    # common methods with a function, since generally the only scenario where
    # overriding is needed is when using code that is not part of the current code base.

    def base_app_methods(app: beaker.Application) -> None:
        @app.external
        def same_signature(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
            ...


    app = beaker.Application("DerivedApp").apply(base_app_methods)


    @app.external(override=True)
    def same_signature(a: pyteal.abi.Uint64, b: pyteal.abi.Uint64):
        ...

For example in ``0.x`` an override with a different signature looks like this:

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

    def base_app_methods(app: beaker.Application) -> None:
        @app.external(name="silly_walk")
        def different_signature(a: pyteal.abi.Uint64):
            ...

    app = beaker.Application("DerivedApp").apply(base_app_methods)

    # remove method defined by base_app_methods
    # note that we use the method signature here
    app.deregister_abi_method("silly_walk(uint64)")

    # add our new method
    @app.external(name="silly_walk")
    def different_signature(a: pyteal.abi.Uint32, b: pyteal.abi.Uint32):
        ...

In the case of overriding a bare method to replace it with an ABI method:

.. code-block:: python

    def base_app_methods(app: beaker.Application) -> None:
        @app.no_op(name="something_completely_different")
        def different_signature():
            ...

    app = beaker.Application("DerivedApp").apply(base_app_methods)

    # remove method defined by a base_app_methods
    # note that we use the completion type here
    app.deregister_bare_method("no_op")

    # add our new method
    @app.external(name="something_completely_different")
    def different_signature(x: pyteal.abi.Uint32):
        ...


Logic signatures
----------------

With version ``1.0`` a logic signature is no longer defined by inheriting ``beaker.LogicSignature``, instead
``LogicSignature`` is instantiated directly, and the PyTeal expression - or a function returning an expression - is passed as an argument.

For example in ``0.x`` this code:

.. code-block:: python

    class MySignature(beaker.LogicSignature):
        def evaluate(self) -> pyteal.Expr:
            return pyteal.Approve()

    my_signature = MySignature()

Becomes the following in ``1.0``:

.. code-block:: python

    def evaluate() -> pyteal.Expr:
        return pyteal.Approve()

    my_signature = beaker.LogicSignature(evaluate)

or equivalently:

.. code-block:: python

    my_signature = beaker.LogicSignature(pyteal.Approve())

The key changes to note above:

1. There is no sub-classing, instead a ``beaker.LogicSignature`` instance is created.
2. A function returning a PyTeal expression (or perhaps more simply just a PyTeal expression) is passed to ``LogicSignature``
   instead of implementing ``def evaluate(self)``.

Runtime Templated Logic signatures
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In ``0.x`` logic signatures could be created with the ability to substitute templated variables on-chain at runtime using ``beaker.TemplateVariable``.

With version ``1.0`` a logic signature with a runtime templated value is no longer defined by inheriting ``beaker.LogicSignature``, instead
``LogicSignatureTemplate`` is instantiated directly, and the PyTeal expression and a dictionary of template variables
are passed as arguments.

For example in ``0.x`` this code:

.. code-block:: python

    class MySignature(beaker.LogicSignature):

        some_value = beaker.TemplateVariable(pyteal.TealType.uint64)

        def evaluate(self):
            return pyteal.Return(self.some_value)

    my_signature = MySignature()

Becomes this in ``1.0``:

.. code-block:: python

    def evaluate(some_value: pyteal.Expr):
        return pyteal.Return(some_value)

    my_signature = beaker.LogicSignatureTemplate(
        evaluate,
        runtime_template_variables={"some_value": pyteal.TealType.uint64},
    )

The key changes to note are:

1. There is no sub-classing, instead a ``beaker.LogicSignatureTemplate`` instance is created.
2. A function returning a PyTeal expression (or just an expression) is passed to ``LogicSignatureTemplate``
   instead of implementing ``def evaluate(self)``.
3. A dictionary of template variable name and types is passed instead of instantiating ``beaker.TemplateVariable``
   for each variable.
4. The template variables are provided as arguments to the evaluation function. The function can omit these arguments
   if they are not used.

Precompiled signatures and applications
---------------------------------------

In ``0.x`` logic signatures and applications could be precompiled by adding an ``AppPrecompile`` or
``LSigPrecompile`` attribute to the application class, making certain properties available for use inside
the application's methods like the logic hash and the TEAL code.

In ``1.0``, you do not need to reference any "precompile classes" directly, instead you must use the ``beaker.precompiled`` function.

For example in ``0.x``, a precompile might look like this:

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
by keyword only, for example this code in ``0.x``:

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
                 pt.Txn.sender() == self.pc.logic.template_hash(pt.Int(template_value))
             )

Could be expressed like this in ``1.0``:

.. code-block:: python

    lsig = beaker.LogicSignatureTemplate(
        lambda tv: pyteal.Seq(pyteal.Assert(tv), pyteal.Int(1)),
        runtime_template_variables={"tv": pyteal.TealType.uint64},
    )

    app = beaker.Application("App")


    @app.external
    def check_it() -> pyteal.Expr:
        lsig_pc = beaker.precompiled(lsig)
        return pyteal.Assert(
            pyteal.Txn.sender() == lsig_pc.address(tv=pyteal.Int(template_value))
        )

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

    import beaker.precompile
    import algosdk.atomic_transaction_composer

    signature = beaker.LogicSignature(...)

    precompiled_signature = beaker.precompile.PrecompiledLogicSignature(
        signature, client=...
    )
    signer = algosdk.atomic_transaction_composer.LogicSigTransactionSigner(
        algosdk.transaction.LogicSigAccount(precompiled_signature.logic_program.raw_binary)
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

    import beaker.precompile
    import algosdk.atomic_transaction_composer

    signature = beaker.LogicSignatureTemplate(
        lambda tv: ..., runtime_template_variables={"tv": pyteal.TealType.uint64}
    )

    precompiled_signature = beaker.precompile.PrecompiledLogicSignatureTemplate(
        signature, client=...
    )
    signer = algosdk.atomic_transaction_composer.LogicSigTransactionSigner(
        algosdk.transaction.LogicSigAccount(precompiled_signature.populate_template(tv=123))
    )

State related classes and methods
---------------------------------

Version ``1.0`` of Beaker renames existing state related to classes to follow the naming conventions
used more generally within existing Algorand and TEAL documentation. Generally the renames involved changing
``Application`` to ``Global`` and ``Account`` to ``Local``. While ``Application`` and ``Account`` more accurately
reflect the use of those state values, the deviance to the rest of the Algorand ecosystem was felt to be a bigger
usability and understandability issue.

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

A number of internal modules in ``beaker.lib`` were collapsed for simplicity. The following is a list of affected modules:

* ``beaker.lib.inline.inline_asm.*`` -> ``beaker.lib.inline.*``
* ``beaker.lib.iter.iter.*`` -> ``beaker.lib.iter.*``
* ``beaker.lib.math.math.*`` -> ``beaker.lib.math.*``
* ``beaker.lib.strings.string.*`` -> ``beaker.lib.string.*``
