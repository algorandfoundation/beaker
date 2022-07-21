Usage
=====

.. _installation:

Installation
------------

Currently only installing from github is supported:

.. code-block:: console

    (.venv)$ pip install git+https://github.com/algorand-devrel/beaker


.. _hello_beaker:

Hello, Beaker 
-------------

First, create a class to represent our application as a subclass of the beaker `Application`. 

.. code-block:: python

    from beaker import Application

    class MySickApp(Application):
        pass 


This is a full application, though it doesn't do much.  Instantiate it and take a look at some of the resulting fields. 

.. code-block:: python

    import json

    msa = MySickApp()
    print(f"Approval program: {msa.approval_program}")
    print(f"Clear program: {msa.clear_program}")
    print(f"Contract Spec: {json.dumps(msa.contract.dictify())}")


Nice!  This is already enough to provide the TEAL programs and ABI specification.

Lets add a method to be handled by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/>`_ method with with the `handler` decorator. 

.. code-block:: python

    from pyteal import *
    from beaker import Application, handler

    class MySickApp(Application):

        @handler
        def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            return output.set(a.get() + b.get())


The ``@handler`` decorator adds an ABI method with signature ``add(uint64,uint64)uint64`` to our application and includes it in the routing logic for handling an ABI call. 

The python method must return an ``Expr`` of some kind, invoked when the handler is called. 

.. note::
    ``self`` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like ``MySickApp.do_thing(data)``

Lets now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. code-block:: python

    from algosdk.atomic_transaction_composer import  AccountTransactionSigner 
    from pyteal import abi 

    # utils to connect to sandbox kmd and pull all accounts and init an algod client
    from beaker import Application, handler, sandbox
    from beaker.client import ApplicationClient 

    class MySickApp(Application):
        @handler
        def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
            return output.set(a.get() + b.get())

    # Get the first account from the sandbox KMD 
    addr, private_key = sandbox.get_accounts().pop()
    signer = AccountTransactionSigner(private_key)

    # Instantiate our app
    msa = MySickApp()

    # Create ApplicationClient
    app_client = ApplicationClient(sandbox.get_client(), msa, signer=signer)

    # Call `create`  
    app_id, app_addr, tx_id = app_client.create()
    print(f"Created app with id: {app_id} and address: {app_addr}")

    # Call the `add` method 
    result = app_client.call(msa.add, a=2, b=3)
    print(result.return_value) # 5


Thats it! Invoking ``create``, the ``ApplicationClient`` constructs an appropriate ApplicationCallTransaction, signs it with the ``signer`` passed, and submits it to the network.

.. note:: 
    Once created, subsequent calls to the app_client are directed to the ``app_id``. 
    The constructor may also be passed an app_id directly if one is already deployed.

After creation, we use ``app_client.call``, passing the method defined in our class and args the method specified (by name). 

.. note::
    The args passed must match the type of the method (i.e. don't pass a string when it wants an int). 

The result contains the parsed ``return_value`` which should match the type the ABI method returns.


.. _manage_state:

Managing State
--------------

Beaker provides a way to define state values as class variables and use them throughout our program. This is a convenient way to encapsulate functionality associated with some state values.

.. note:: 
    Througout the examples we tend to mark State Values as ``Final[...]``, this is solely for good practice and has no effect on the output of the program.


Lets add some Application State (or `Global State <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ in Algorand parlance) to our Application. 

.. code-block:: python

    from typing import Final
    from pyteal import *
    from beaker import *

    class MySickApp(Application):
        counter: Final[ApplicationStateValue] = ApplicationStateValue(
            stack_type=TealType.uint64,
            descr="A counter meant to show use of application state",
            key=Bytes("cnt"),   # Override the default key (class var name) 
            default=Int(5),     # Initialize to 5 
            static=True,        # Once set, prevent overwrite 
        )

        @handler
        def increment(self, *, output: abi.Uint64):
            return Seq(
                self.counter.set(self.counter + Int(1)),
                output.set(self.counter)
            )

        @handler
        def decrement(self, *, output: abi.Uint64):
            return Seq(
                self.counter.set(self.counter - Int(1)),
                output.set(self.counter)
            )

We've added an :ref:`ApplicationStateValue <application_state>` attribute to our class with several configuration options.

We can now reference it by name in the new methods we've added!  These new methods may be called by the application client just like the ``add`` method above.  

.. note:: 
    The base ``Application`` class has several handlers pre-defined, including ``create`` which performs ``ApplicationState`` initialization for us, setting the keys to default values.


:ref:`AccountState <account_state>` (or Local storage) and even allow for dynamic state keys.

.. code-block:: python

    from beaker import AccountStateValue

    class MyTagTrackerApp(Application):

        nickname: Final[AccountStateValue] = AccountStateValue(
            stack_type=TealType.bytes, 
            descr="What this user prefers to be called"
        )

        tags: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
            stack_type=TealType.uint64,
            max_keys=10,
        )

        @handler
        def set_nickname(self, nickname: abi.String):
            return self.nickname.set(nickname.get())

        @handler
        def add_tag(self, tag: abi.String):
            return self.tags[tag.get()].set(Int(1))

This application just allows a user to set their nickname and add tags. The ``tags`` class variable is a ``DynamicAccountStateValue``, allowing for accessing custom keys using the ``[...]`` notation.

.. _inheritance:

Inheritance 
-----------

What about extending our Application with some other functionality?

.. code-block:: python

    from beaker.contracts import OpUp
    from beaker.decorators import handler

    class MyHasherApp(OpUp):
        @handler
        def hash_it(
            self,
            input: abi.String,
            iters: abi.Uint64,
            opup_app: abi.Application,
            *,
            output: abi.StaticArray[abi.Byte, Literal[32]],
        ):
            return Seq(
                Assert(opup_app.application_id() == self.opup_app_id),
                self.call_opup(Int(255)),
                (current := ScratchVar()).store(input.get()),
                For(
                    (i := ScratchVar()).store(Int(0)),
                    i.load() < iters.get(),
                    i.store(i.load() + Int(1)),
                ).Do(current.store(Sha256(current.load()))),
                output.decode(current.load()),
            )

Here we subclassed the ``OpUp`` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.