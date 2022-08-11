# Hello Developer

If you've written and deployed a Smart Contract for Algorand using PyTeal before today, you've probably chewed a lot of glass to do so.  You've overcome a number of technical limitations and struggled through parsing obscure error messages, well done. 

Take heart that the Algorand team has been working very hard to improve the development experience. 

Before we dive in to the improvements, lets review some common things folks struggle with while developing.

## Code Organization

When you start writing a contract, how should you structure the logic? How should you handle inputs and outputs from the contract? 

A very common pattern is something like:

```py

    def approval():
        #...
        return Cond(
            # Infer that this is create 
            [Txn.application_id() == Int(0), do_create_method()],
            # Check on complete manually
            [Txn.on_complete() == OnComplete.UpdateApplication, do_update()],
            # Use some const that you have to somehow communicate to the caller 
            # to route to the right method, then figure out how to parse the rest 
            # of the app args
            [Txn.application_args[0] == "do_the_thing", do_the_thing()],
            #...
        )

    # ...
    approval_teal = compileTeal(approval(), mode=Mode.Application, version=6)

``` 

This works, but is far from obvious to a newcomer. 


## Interacting with the Application

To create the application on-chain you need to compile the teal programs then create a transaction with the programs,  schema ("How many global uints do I need again?"), and extra pages. 

Calling the application involves crafting transactions with the appropriate routing and data arguments if not using the ABI.

Even when using the ABI, calling methods involves importing the json contract and constructing an AtomicTransactionComposer passing args as list with no context about what they should be.


## Managing State 

Managing state schema is often done manually with constants for the keys and remembering what the type associated should be. 

Creating the application requires you to know the number and type of each state value which you have no easy way to get automatically.

## Debugging

Debugging can be a nightmare of trying to figure out an error message like `assert failed: pc=XXX` 

<img src="pc-load-letter-pc.gif" alt="pc load letter??" style="width:200px">


## Testing

Testing contracts is difficult and requires rebuilding a lot of the front end infrastructure to test different inputs/outputs. 


# The devs did something 

Now, let's see how things have changed.

## ABI

The [ABI](https://arc.algorand.foundation/ARCs/arc-0004) provides standards for encoding types, describing methods, and internally routing method calls to the appropriate logic.

With the ABI we have a standard way to both organize code and interact with the application. 

More details on the ABI are available [here](https://developer.algorand.org/articles/contract-to-contract-calls-and-an-abi-come-to-algorand/)

## Atomic Transaction Composer

Using the [Atomic Transaction Composer](https://developer.algorand.org/docs/get-details/atc/) and the the ABI spec for your contract, you can easily compose atomic group transactions and have the arguments encoded and return values decoded for you!

## Pyteal ABI

PyTeal now provides the necessary components to handle encoding/decoding of types in a contract.  The PyTeal `Router` class even provides a way to route method handling logic and passing decoded types directly to a method as well as providing the ABI contract spec.

For example, if you want to create and handle a method that adds 1 to a uint8 you can do so thusly: 

```py
@router.method
def increment_my_number(input: abi.Uint8, *, output: abi.Uint8):
    return output.set(input.get() + Int(1))
```

<img src="face_touch.png" alt="facetouch" style="width:100px">

So. Much. Nicer.

For more background see the blog post [here](https://medium.com/algorand/pyteal-introduces-abi-support-for-smart-contracts-605153e91c5e)

For detailed docs on PyTeal ABI see docs [here](https://pyteal.readthedocs.io/en/stable/abi.html)

## Source Maps

Getting a `pc` returned from an algod error message meant you had to assemble, then disassemble your teal contract to find the TEAL line it might be associated to. Even then the names and formatting is mangled in the process so it was hard to track exactly where you were in your program.

You can now compile TEAL with the `sourcemap` flag [enabled](https://developer.algorand.org/docs/rest-apis/algod/v2/#post-v2tealcompile).  The resulting map comes back according to [this spec](https://sourcemaps.info/spec.html) and can be decoded with any of the SDKs using the new `SourceMap` object.

This means you can associate a `pc` directly to the source TEAL line with all the familiar names and formatting you're used to looking at.


# Hello Beaker

Today we are sharing [Beaker](https://github.com/algorand-devrel/beaker), a Smart Contract development framework meant to improve the development experience. 

Beaker takes advantage of the above improvements, allowing us to provide much more structure to applications. 

Heads up though, it is still experimental.

<img src="beaker_fire.jpg" alt="beaker fire" style="width:300px">


Full Docs are [here](https://algorand-devrel.github.io/beaker/html/index.html).

Taking the above issues, lets see how Beaker helps.

## Code Organization

Beaker provides standard way to organize code using a class to encapsulate functionality.

```py
from beaker import Application, external

class MyApp(Application):
    @external
    def add(self, a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64):
        return output.set(a.get() + b.get())
```

This is a full application! It's got an `approval program`, `clear program`, an implicitly empty `state` and provides the ABI `contract` to export for other clients.

The `@external` decorator on the method exposes our defined method to callers and provides routing based on its `method selector`. The resulting method signature of this method is `add(uint64,uint64)uint64`.

The method that has been tagged is a (mostly) valid [PyTeal ABI Method](https://pyteal.readthedocs.io/en/stable/abi.html#subroutines-with-abi-types). The exception here is that Beaker allows you to pass `self`, meaning you can take advantage of instance vars passed on initialization.

There is much more you can do with it including [access control](https://algorand-devrel.github.io/beaker/html/decorators.html#authorization), changing which `OnComplete` types may be used to call it, or marking it as a `read-only` method.

For more see the [Decorator docs](https://algorand-devrel.github.io/beaker/html/decorators.html)

## Interacting with the application

Beaker provides an `ApplicationClient` to deal with the common needs like creation/opt-in/calling methods.


It uses your `Application` definition to provide context like the schema or the arguments required for the methods being called.

```py
from beaker import sandbox, client

app = MyApp()

# get the first acct in the sandbox
acct = sandbox.get_accts().pop()

app_client = client.ApplicationClient(sandbox.get_algod_client(), app, signer=acct.signer)

# deploy the app on-chain
app_client.create()

# call the method
result = app_client.call(app.add, a=32, b=10)
print(result.return_value) # 42

# now go outside and touch some grass cuz you're done
```

For more see [ApplicationClient docs](https://algorand-devrel.github.io/beaker/html/application_client.html)

## Managing state

Beaker allows you to declare typed state values as class variables.

```py
from beaker import Application, ApplicationStateValue, external
class CounterApp(Application):
    counter = ApplicationStateValue(TealType.uint64)

    @external
    def incr_counter(self, incr_amt: abi.Uint64):
        self.counter.set(self.counter + incr_amt.get())
```

We can even inspect our application to see what its schema requirements are!

```py
app = CounterApp()
print(app.app_state.schema())
```

For more see [State docs](https://algorand-devrel.github.io/beaker/html/state.html)

## Debugging

Beaker improves the `pc=xxx` error message using the source map endpoint during compilation and mapping the pc back to the source teal. The resulting LogicError allows you to see the exact source Teal line number with all the useful names of subroutines and any comments in the source teal.

This is an actual print from a logic error that tells me exactly where my program failed and the context provided from the source TEAL shows me _why_ it failed.
```
Txn WWVF5P2BXRNQDFFSGAGMCXJNDMZ224RJUGSMVPJVTBCVHEZMOMNA had error 'assert failed pc=883' at PC 883 and Source Line 579: 

        store 50
        store 49
        store 48
        store 47
        // correct asset a
        load 50
        txnas Assets
        bytec_0 // "a"
        app_global_get
        ==
        assert          <-- Error
        // correct asset b
        load 51
        txnas Assets
        bytec_1 // "b"
        app_global_get
        ==
        assert
        // correct pool token
        load 49
```

We're also working on getting this mapping all the way back to the source PyTeal with this [issue](https://github.com/algorand/pyteal/issues/449)

## Testing

Initially Beaker provides helpers for:

1) Retrieving and comparing account balances.  
2) Unit testing functionality by passing inputs and comparing to expected outputs.

For more see [Testing docs](https://algorand-devrel.github.io/beaker/html/testing.html) for more.

## More

There is a lot more not covered here and a lot still to be done. 

See the docs at https://beaker.algo.xyz 

The code at https://github.com/algorand-devrel/beaker

And for any questions, ping `@barnji` in the `#beaker` channel on the [Algorand discord](https://discord.gg/algorand)

I want all the feedback.


# TL;DR

Be like this truly inspiring golden retriever, use Beaker.

*Before Beaker*

<img src="dog_before.png" alt="dog before" style="width:300px">

*After Beaker*

<img src="dog_after.png" alt="dog after" style="width:300px">
