Beaker
------

![Beaker](beaker.png)

Beaker is a smart contract development framework for PyTeal inspired by Flask

*Experimental - subject to change* 

With Beaker, you build a class that represents your entire application including state and routing.

## Install

First install Beaker:

`pip install git+https://github.com/algorand-devrel/beaker`

## Quick Start

See `examples/my_sick_app` for runnable source

First, create a class to represent your application and specify the `beaker.Application` as its parent. 

```py
from beaker import Application

class MySickApp(Application):
    ...
```

Now, add a method to be handled by your application. This is done by tagging a valid PyTeal ABI method with with the `handle` decorator. More on this later.

```py
from pyteal import *
from beaker import Application, handle

class MySickApp(Application):

    @handler
    def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        return output.set(a.get() + b.get())

```

Now instantiate it and take a look at some of the resulting fields.

```py

import json

msa = MySickApp()
print(f"Approval program: {msa.approval_program}")
print(f"Clear program: {msa.clear_program}")
print(f"Contract Spec: {json.dumps(msa.contract.dictify())}")

```

Nice!

Lets now deploy our contract

```py

from algosdk.v2.algod import AlgodClient
from algosdk.atomic_transaction_composer import  AccountTransactionSigner 

from beaker import ApplicationClient 

# definition of get_account omitted but you get the idea 
addr, private_key = get_account()
signer = AccountTransactionSigner(private_key)

# Connect to local sandbox
client = AlgodClient("a"*64, "http://localhost:4001")

# Instantiate our app
msa = MySickApp()

# Create an app client with he client and an instance of the app
app_client = ApplicationClient(client, msa)

# Call the `create` method, passing the signer. 
app_id, app_addr, txid = app_client.create(signer)
print(f"Created app with id: {app_id} and address: {app_addr}")

```

Thats it! The `ApplicationClient` handles constructing the ApplicationCallTransaction with the appropriate parameters, signs it with the `signer` passed, and submits it to the network.  Once called the app_client has its internal `app_id` set so subsequent calls are directed to that app id. The initial constructor may also be passed an app_id if one is already deployed. Methods for `delete` and `update` are also available. 


Now we can call the method we defined

```py

result = app_client.call(signer, msa.add.method_spec(), [2,3])
print(result.abi_results[0].return_value) # 5

```

Here we use the `app_client.call` method, pass the signer and the `Method` object which is available through the Application object and provides the information for the client to encode the arguments appropriately.

Lets go back and add some application state (global state in Algorand parlance). 

```py

from beaker import ApplicationState, GlobalStateValue

class MySickAppState(ApplicationState):
    counter = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="A counter for showing how to use application state",
    )

class MySickApp(Application):
    app_state: Final[MySickAppState] = MySickAppState()

    @handler
    def increment(*, output: abi.Uint64):
        return Seq(
            MySickApp.app_state.counter.set(MySickApp.app_state.counter + Int(1)),
            output.set(MySickApp.app_state.counter)
        )

    @handler
    def decrement(*, output: abi.Uint64):
        return Seq(
            MySickApp.app_state.counter.set(MySickApp.app_state.counter - Int(1)),
            output.set(MySickApp.app_state.counter)
        )
```

These methods may be called in the same way as the `add` method above. Note that you can refer to the state using the class name. Using `set` we can overwite the value that is currently stored.

But what if we only want certain callers to be allowed? Lets add a parameter to the handler to allow only the app creator to call this method.

```py
    from beaker import Authorize

    #...

    @handler(authorize=Authorize.only(Global.creator_address()))
    def increment(*, output: abi.Uint64):
        return Seq(
            MySickApp.app_state.counter.set(MySickApp.app_state.counter + Int(1)),
            output.set(MySickApp.app_state.counter)
        )
```

This parameter may be any Subroutine that accepts a sender as its argument and returns an integer interpreted as true/false.  Other pre-defined Authorized checks are for whether or not the sender holds a given asset and whether or not they're opted in to some app. 

The `handler` decorator accepts several other parameters:

- `method_config` - See the PyTeal definition for more, but tl;dr it allows you to specify which OnCompletes may handle different modes (call/create/none/all)
- `read_only` - Really just a place holder until arc22 is merged


We can also specify Account state and even account for dynamic state

```py
from beaker import AccountState, LocalStateValue

class MySickAcctState(AccountState):
    nickname=LocalStateValue(stack_type=TealType.bytes, descr="What this user prefers to be called")
    tags=DynamicLocalStateValue(
        stack_type=TealType.bytes,
        max_keys=10,
        key_gen=Subroutine(TealType.uint64, name='make_key')(
            lambda v: Concat(Bytes("tag:"), v)
        )
    )

class MySickApp(Application):

    acct_state: Final[MySickAcctState] = MySickAcctState()

    @handler
    def add_tag(tag: abi.String):
        # Set `tag:$tag` to 1
        return MySickApp.acct_state.tags(tag.get()).set(Txn.sender(), Int(1))

```

That's it for now. Please file issues with ideas or descriptions of how this might not work for your use case.

