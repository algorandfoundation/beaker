Beaker
------
<img align="left" src="beaker.png" margin="10px" >

Beaker is a smart contract development framework for [PyTeal](https://github.com/algorand/pyteal) inspired by Flask


With Beaker, we build a class that represents our entire application including state and routing.

*Experimental - Mostly Untested - subject to change* 


## Install

Currently only installing from github is supported

`pip install git+https://github.com/algorand-devrel/beaker`

See [examples](/examples/) for runnable source

## Hello Beaker 

First, create a class to represent our application as a subclass of the beaker `Application`. 

```py
from beaker import Application

class MySickApp(Application):
    pass 
```

This is a full application, though it doesn't do much.

Instantiate it and take a look at some of the resulting fields. 

```py

import json

msa = MySickApp()
print(f"Approval program: {msa.approval_program}")
print(f"Clear program: {msa.clear_program}")
print(f"Contract Spec: {json.dumps(msa.contract.dictify())}")

```

Nice!  This is already enough to provide the TEAL programs and ABI specification.

We can add a method to be handled by the application. This is done by tagging a valid PyTeal ABI method with with the `handler` decorator. More on this later.

```py
from pyteal import *
from beaker import Application, handler

class MySickApp(Application):

    @handler
    def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        return output.set(a.get() + b.get())

```

Tagging the method with the `@handler` decorator adds an ABI method with signature `add(uint64,uint64)uint64` to our application. The python method must return an `Expr` of some kind, which is invoked when the handler is called. 

> Note: `self` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like `MySickApp.do_thing(data)`

## Application Client

Lets now deploy our contract using an `ApplicationClient`.

```py

from algosdk.atomic_transaction_composer import  AccountTransactionSigner 

# utils to connect to sandbox kmd and pull all accounts and init an algod client
from beaker.sandbox import get_accounts, get_client
from beaker.client import ApplicationClient 

# Get the accounts from the sandbox KMD 
addr, private_key = get_accounts().pop()
signer = AccountTransactionSigner(private_key)

# Get algod client for local sandbox
client = get_client()

# Instantiate our app
msa = MySickApp()

# Create an app client with he client and an instance of the app, 
# also specifying signer here but it can be passed directly later on
# if a different signer is required
app_client = ApplicationClient(client, msa, signer=signer)

# Call the `create` method. 
app_id, app_addr, tx_id = app_client.create()
print(f"Created app with id: {app_id} and address: {app_addr}")

```

Thats it! The `ApplicationClient` handles constructing the ApplicationCallTransaction with the appropriate parameters, signs it with the `signer` passed, and submits it to the network.  

Once created, subsequent calls to the app_client are directed to the `app_id`. The constructor may also be passed an app_id directly if one is already deployed.  Methods for `.delete()`/`.update()`/`.opt_in()`/`.close_out()`/`.clear_state()`  are also available. 


Now, we can call the method we defined in our `Application`

```py
result = app_client.call(msa.add, a=2,b=3)
print(result.return_value) # 5
```

We use the `app_client.call` method, passing the method defined in our class as well as args the method specified by name. The args passed must match the type of the method (i.e. don't pass a string when it wants an int). 

The result contains the parsed `return_value`, a `decode_error` if necessary and the `raw_value`, useful if there  is a `decode_error`.

The Application Client also provides for composing multiple app calls with the `app_client.add_method_call`, passing a pre-existing AtomicTransactionComposer.

## Managing State

With Beaker, we can define state values as class variables and use them throughout our program. This provides a convenient way to reference specific values and can be used to encapsulate functionality. 

> Note:  below we tend to mark State Values as `Final[StateValue]`, this is solely for good practice and has no effect on the output of the program.

### Application State

Lets go back and add some Application State (or Global State in Algorand parlance). 

```py
from typing import Final
from pyteal import *
from beaker import *

class MySickApp(Application):
    # Mark it `Final` to signal that we shouldn't change the python class variable
    # This has _no_ effect on the generated TEAL, its purely a python level
    # demarcation for the reader/writer of the contract
    counter: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        descr="A counter meant to show use of application state",
        key=Bytes("counter"), # Override the default key (class var name) 
        default=Int(5), # Initialize to 5 
        static=True, # Once set, prevent overwrite 
        # Note: `static` is enforced _only_ while using methods defined on the StateVarr
        # it _could_ still be changed if we use the `App.globalSet`, but don't do that
    )

    # Note the method name needs to be `create` exactly to 
    # override the implementation in the Application class
    @create
    def create(self):
        return self.initialize_app_state()

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
```

The `create` method overrides the one defined in the base `Application` class, tagging it with `@create` which specifies we want a bare call (no app args) and only on create (app id == 0). [See Bare Handlers for more](#bare-handlers).

These new methods may be called by the application client just like the `add` method above.  

We initialize the application state during creation. This automatically sets any default values specified at the key specified, otherwise it uses the field name. Referencing the field directly is the same as loading the value from global storage. We use the `set` method of ApplicationStateValue to overwrite the value that is currently stored. If the state value is marked as `static` an attempt to call `set` _after_ it already contains a value, it will Assert and fail the program.  This can be circumvented easily using `App.globalSet` directly, the `static` flag is not something enforced at the protocol level.

We can call  `.increment()`/`.decrement()` directly as long as its a `TealType.uint64`. The value can be retrieved using `.get()`/`.get_must()`/`.get_maybe()`/`.get_else()` depending on the circumstance.

### Account State

We can specify Account state and even allow for dynamic state keys.

```py
from beaker import AccountStateValue

# A subroutine that takes bytes and returns bytes
# to be used as a key-generator (optional)
@Subroutine(TealType.bytes)
def make_tag_key(tag):
    return Concat(Bytes("tag:"), tag)

class MySickApp(Application):

    nickname: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.bytes, 
        descr="What this user prefers to be called"
    )
    tags: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=10,
        key_gen=make_tag_key # optional
    )

    @handler
    def add_tag(self, tag: abi.String):
        # Set `tag:$tag` to 1 for Txn.sender()

        # Accesses the `AccountStateValue` with the key matching the value
        # passed into square brackets and sets the value

        # we can override who's state to set with the argument `acct=XXX`
        return self.tags[tag.get()].set(Int(1))

```

## Subclassing

What about extending our Application with some other functionality?

```py
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


```

Here we subclassed the `OpUp` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.


## Handler Arguments

The `handler` decorator accepts several parameters:

- [authorize](#authorization) - Accepts a subroutine with input of `Txn.sender()` and output uint64 interpreted as allowed if the output>0.
- `method_config` - See the PyTeal definition for more, (something like `method_config=MethodConfig(no_op=CallConfig.ALL)`).
- [read_only](#method-hints) - Mark a method as callable with no fee (using Dryrun, place holder until arc22 is merged).
- [resolvable](#resolvable) - Provides a means to resolve some required input to the caller. 

### Authorization

What if we only want certain callers to be allowed? Lets add a parameter to the handler to allow only the app creator to call this method.

```py
    from beaker import Authorize

    #...

    @handler(authorize=Authorize.only(Global.creator_address()))
    def increment(self, *, output: abi.Uint64):
        return Seq(
            self.counter.set(self.counter + Int(1)),
            output.set(self.counter)
        )
```

This parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  

The pre-defined Authorized checks are: 

- `Authorize.only(address)` for allowing a single address access
- `Authorize.has_token(asset_id)` for whether or not the sender holds >0 of a given asset
- `Authorize.opted_in(app_id)`  for whether or not they're opted in to a given app 

But we can define our own

```py
from beaker.consts import algo

@internal(TealType.uint64)
def is_whale(acct: Expr):
    # Only allow accounts with 1mm algos
    return Balance(acct)>Int(1_000_000*algo)

@handler(authorize=is_whale)
def greet(*, output: abi.String):
    return output.set("hello whale")
```

## Method Hints

A Method may provide hints to the caller to help provide context for the call. Currently Method hints are one of:

- [Resolvable](#resolvable) - A hint to _"resolve"_ some required argument
- [Models](#models) - A list of model field names associated to some abi Tuple. 
- Read Only - A boolean flag indicating how this method should be called. Methods that are meant to only produce information, having no side effects, should be flagged as read only. [ARC22](https://github.com/algorandfoundation/ARCs/pull/79)

### Resolvable 

In an above example, there is a required argument `opup_app`, the id of the application that we use to increase our budget via inner app calls. This value should not change frequently, if at all, but is still required to be passed so we may _use_ it in our logic. We can provide a caller the information to `resolve` the appropriate app id using the `resolvable` keyword argument of the handler. 

We can change the handler to provide the hint.

```py
@handler(
    resolvable=ResolvableArguments(
        opup_app=OpUp.opup_app_id 
    )
)
```

With this handler config argument, we communicate to a caller the application expects be passed a value that can bee resolved by retrieving the state value in the application state for `opup_app_id`.  This allows the `ApplicationClient` to figure out what the appropriate application id _should_ be if necessary. 

Options for resolving arguments are:

- A constant, `str | int`
- State Values, `ApplicationStateValue | AccountStateValue (only for sender)`
- A read-only ABI method  (If we need access to a Dynamic state value, use an ABI method to produce the expected value)


Here we call the method, omitting the `opup_app` argument:
```py
input = "hashme"
iters = 10
# In this case we'd like to pass a different signer to call this transaction
signer_client = app_client.prepare(signer=signer)
result = signer_client.call(app.hash_it, input=input, iters=iters)
```

When invoked, the `ApplicationClient` checks to see that all the expected arguments are passed, if not it will check for hints to see if one is specified for the missing argument and try to resolve it by calling the method and setting the value of the argument to the return value of the hint.


### Models

With Beaker we can define a custom structure and use it in our ABI methods.

```py
from beaker.model import Model

class Modeler(Application):

    orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
    )


    class Order(Model):
        item: abi.String
        quantity: abi.Uint32

    
    @handler
    def place_order(self, order_number: abi.Uint8, order: Order):
        return self.orders[order_number].set(order.encode())

    @handler(read_only=True)
    def read_order(self, order_number: abi.Uint8, *, output: Order):
        return output.decode(self.orders[order_number])

```

The application exposes the ABI methods using the tuple encoded version of the fields specified in the model. Here it would be `(string,uint32)`.

A method hint is available to the caller for encoding/decoding by field name. 

```py
    # Passing in a dict as an argument that, according to the ABI, should take a tuple 
    # The keys should match the field names
    order_number = 12
    order = {"quantity": 8, "item": "cubes"}
    app_client.call(app.place_order, order_number=order_number, order=order)

    # Call the method to read the order at the original order number and decode it
    result = app_client.call(app.read_order, order_number=order_number)
    abi_decoded = Modeler.Order().client_decode(result.raw_value)

    assert order == abi_decoded
```


## More?

That's it for now.  

See [TODO](TODO.md) for what is planned.

*Please file issues (Or PRs?) with ideas or descriptions of how this might not work for your use case.*
