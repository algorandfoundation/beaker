Beaker
------

![Beaker](beaker.png)

Beaker is a smart contract development framework for [PyTeal](https://github.com/algorand/pyteal) inspired by Flask

*Experimental - Untested - subject to change* 

With Beaker, you build a class that represents your entire application including state and routing.

## Install

Currently only installing from github is supported

`pip install git+https://github.com/algorand-devrel/beaker`

See [examples](/examples/) for runnable source

## Hello Beaker 

First, create a class to represent your application as a subclass of the beaker `Application`. 

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
from beaker import Application, handle

class MySickApp(Application):

    @handler
    def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        return output.set(a.get() + b.get())

```

This adds an ABI method with signature `add(uint64,uint64)uint64` to our application. The python method should return an `Expr` of some kind to be invoked when the handler is called. 

> Note: `self` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like `MySickApp.do_thing(data)`

## ApplicationClient

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

Once created, subsequent calls to the app_client are directed to the `app_id`. The constructor may also be passed an app_id if one is already deployed.  Methods for `delete` and `update` are also available. 


We can call the method we defined in our `Application`

```py

result = app_client.call(msa.add, a=2,b=3)
print(result.abi_results[0].return_value) # 5

```

Here we use the `call` method, passing the [Method](https://py-algorand-sdk.readthedocs.io/en/latest/algosdk/abi/method.html#algosdk.abi.method.Method) object, and args necessary by name. The args passed may be of any type but must match the definition of the `Method`. 

## Application State

Lets go back and add some application state (Global State in Algorand parlance). 

```py

from beaker import *

class MySickApp(Application):
    counter: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter meant to show use of application state",
        # key=Bytes("counter"), specify a key to override the field name  
        # default=Int(5), specify a default value to initialize the state value to
        # static=True, flag as a value that should not change
    )

    @Bare.create
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

The `create` method overrides the one defined in the base `Application` class, tagging it with `Bare.create` which specifies we want a bare call (no app args) and only on create (app id == 0)

The other methods may be called in the same way as the `add` method above.  Using `set` we can overwrite the value that is currently stored.

But what if we only want certain callers to be allowed? Lets add a parameter to the handler to allow only the app creator to call this method.

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

Other pre-defined Authorized checks are: 

- `Authorize.has_token(asset_id)` for whether or not the sender holds >0 of a given asset
- `Authorize.opted_in(app_id)`  for whether or not they're opted in to a given app 

The `handler` decorator accepts several other parameters:

- `method_config` - See the PyTeal definition for more, but tl;dr it allows you to specify which OnCompletes may handle different modes (call/create/none/all)
- `read_only` - Really just a place holder until arc22 is merged
- `resolvable` - To provide hints to the caller for how to resolve a given input if there is a specific value that should be passed


## Account State

We can also specify Account state and even allow for dynamic state keys.

```py
from beaker import LocalStateValue

@Subroutine(TealType.bytes)
def make_tag_key(tag: abi.String):
    return Concat(Bytes("tag:"), tag.get())

class MySickApp(Application):

    nickname: Final[LocalStateValue] = LocalStateValue(
        stack_type=TealType.bytes, 
        descr="What this user prefers to be called"
    )
    tags: Final[DynamicLocalStateValue] = DynamicLocalStateValue(
        stack_type=TealType.bytes,
        max_keys=10,
        key_gen=make_tag_key
    )

    @handler
    def add_tag(self, tag: abi.String):
        # Set `tag:$tag` to 1
        return self.tags(tag).set(Txn.sender(), Int(1))

```

## Subclassing

Lets say you want to augment an existing application written with Beaker.

```py
from beaker.contracts.arcs import ARC18

class MyRoyaltyApp(ARC18):
    # TODO: add extra methods
    pass

```

You can do so by specifying the parent class then adding or overriding handler methods.


What about just extending your Application with some other functionality?

```py
from beaker.contracts import OpUp
from beaker.decorators import handler

class MyHasherApp(OpUp):
    @handler(
        resolvable = ResolvableArguments(
            opup_app=OpUp.get_opup_app_id
        ) 
    )
    def hash_it(
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application,
        *,
        output: abi.String,
    ):
        return Seq(
            Assert(opup_app.application_id() == OpUp.opup_app_id),
            OpUp.call_opup_n(Int(255)),
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            output.set(current.load()),
        )


```

Here we subclassed the `OpUp` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.

## Method Hints

Note also in the above, the experimental decorator argument,  `resolvable`, adds a `MethodHint` to the method. This allows the `ApplicationClient` to figure out what the appropriate application id _should_ be if necessary.  When using the `ApplicationClient`, omitting the argument for that parameter is equivalent to asking the value to be resolved. 

The line omits the `opup_app` argument:
```py
  input = "hashme"
  iters = 10
  result = app_client.call(app.hash_it, input=input, iters=iters)
```
When invoked, the `ApplicationClient` checks to see that all the expected arguments are passed, if not it will check for hints to see if one is specified for the missing argument and try to resolve it by calling the method and setting the value of the argument to the return value of the hint.


## More?

That's it for now. 

See [TODO](TODO.md) for what is planned.

*Please file issues (Or PRs?) with ideas or descriptions of how this might not work for your use case.*
