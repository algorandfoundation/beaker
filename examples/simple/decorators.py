from pyteal import *
from beaker import *

class ExternalExample(Application):

    @external(no_op=CallConfig.CREATE)
    def create(self, input: abi.String, *, output: abi.String):
        return output.decode(input.encode())

def demo():

    app_client = client.ApplicationClient(sandbox.get_algod_client(), ExternalExample(), signer=sandbox.get_accounts().pop().signer)
    app_client.create()
    #result = app_client.call(ExternalExample.create, input="yo")
    #print(result.return_value)

if __name__ == "__main__":
    demo()