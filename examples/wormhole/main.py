import pyteal as pt
from beaker import *
from beaker.contracts.wormhole import ContractTransferVAA, WormholeTransfer

class OracleReceiver(WormholeTransfer):

    def handle_transfer(self, ctvaa: ContractTransferVAA, *, output: pt.abi.DynamicBytes)->pt.Expr:
        return output.set(ctvaa.payload) 


def demo():
    o = OracleReceiver()    
    print(o.application_spec())

if __name__ == "__main__":
    demo()
