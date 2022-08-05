Hello, Beaker
--------------

# Intro

Hello, Developer.

If you've written and deployed a Smart Contract for Algorand using PyTeal before today, you've probably chewed a lot of glass to do so.  You've overcome a number of technical limitations and struggled through parsing obscure error messages, well done. 

The Algorand team has been working very hard to improve the development experience, but before we dive in, lets review some common things folks struggle with while developing.

## Code Organization
When you start writing a contract, how should you structure the logic? How should you handle inputs and outputs from the contract? 

A very common pattern is something like:

```py

    def approval():
        #...
        return Cond(
            [Txn.application_id() == Int(0), do_create_method()],
            [Txn.on_complete() == OnComplete.UpdateApplication, do_update()],
            [Txn.application_args[0] == "doit", doit()],
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


# Improvements 

Now let's see how things have changed.

## ABI

The [ABI](https://arc.algorand.foundation/ARCs/arc-0004) provides standards for encoding types, describing methods, and internally routing method calls to the appropriate logic.

With the ABI we have a standard way to both organize code and interact with the application. 

More details on the ABI are available [here](https://developer.algorand.org/articles/contract-to-contract-calls-and-an-abi-come-to-algorand/)


## Pyteal ABI

PyTeal now provides the necessary components to handle encoding/decoding of types and describe methods that should be exposed externally.  The PyTeal `Router` even provides a way to route method handling logic and passing decoded types directly to a method.

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



# Beaker

The above improvements allow us to provide much more structure to applications. 

Today we are sharing [Beaker](https://github.com/algorand-devrel/beaker), a Smart Contract development framework meant to improve the development experience. 

Heads up though, it is still experimental.

<img src="beaker_fire.jpg" alt="beaker fire" style="width:300px">



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

This is a full application! Not a `Cond` in sight.


## Interacting with the application
Beaker provides an `ApplicationClient` to deal with the common needs like creation/opt_in/calling methods.


It uses your `Application` definition to provide context like the schema or the arguments required for the methods being called.

```py
from beaker import sandbox, client

accts = sandbox.get_accts()

_, _, signer = accts.pop()

app = MyApp()

app_client = client.ApplicationClient(sandbox.get_algod_client(), app, signer=signer)
# Create the app using its definition including any state schema defined
app_client.create()

result = app_client.call(app.addr, a=31, b=10)
print(result.return_value) # 41
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


## Debugging

Beaker improves the `pc=xxx` error message using the source map endpoint during compilation and mapping the pc back to the source teal. The resulting LogicError allows you to see the exact source Teal line number with all the useful names of subroutines and any comments in the source teal.

The pr [here](https://github.com/algorand/go-algorand/pull/4322) should also help 

## Testing

Initially Beaker provides helpers for validating account balances. More testing infrastructure is needed. 


# TL;DR

Be like dog, use Beaker.

*Before Beaker*

<img src="dog_before.png" alt="dog before" style="width:300px">

*After Beaker*

<img src="dog_after.png" alt="dog after" style="width:300px">
