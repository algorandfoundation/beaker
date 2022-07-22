Beaker
------
<img align="left" src="beaker.png" margin="10px" >

Beaker is a smart contract development framework for [PyTeal](https://github.com/algorand/pyteal) inspired by Flask


With Beaker, we build a class that represents our entire application including state and routing.

*Mostly Untested - Expect Breaking Changes* 

*Please feel free to file issues/prs*

## Hello, Beaker


```py
from pyteal import *
from beaker import *

class MySickApp(Application):
    @handler
    def hello(name: abi.String, *, output: abi.String):
        return output.set(Concat(Bytes("Hello, "), name.get()))

if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import AccountTransactionSigner
    from beaker import sandbox, client

    msa = MySickApp()

    addr, secret = sandbox.get_accounts().pop()
    signer = AccountTransactionSigner(secret)

    app_client = client.ApplicationClient(sandbox.get_client(), msa, signer=signer)
    app_id, app_addr, txid = app_client.create()

    result = app_client.call(msa.hello, name="Beaker")
    print(result.return_value) # Hello, Beaker
```

## Install

Currently only installing from github is supported

`pip install git+https://github.com/algorand-devrel/beaker`

## Use

[Examples](/examples/)

[Docs](https://beaker.algo.xyz)

[TODO](TODO.md)