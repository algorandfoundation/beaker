from typing import Literal
from abc import ABC, abstractclassmethod
from beaker import Application, external
from pyteal import (
    Reject,
    abi,
    Expr,
    Seq,
    ScratchVar,
    Int,
    Suffix,
)


def move_offset(offset: ScratchVar, t: abi.BaseType) -> Expr:
    return offset.store(offset.load() + Int(t.type_spec().byte_length_static()))



class ContractTransferVAA:
    def __init__(self):
        # fmt: off
        self.version        = abi.Uint8()    #: Version of VAA
        self.index          = abi.Uint32()   #: Which guardian set to be validated against
        self.siglen         = abi.Uint8()    #: How many signatures
        self.timestamp      = abi.Uint32()   #: TS of message
        self.nonce          = abi.Uint32()   #: Uniquifying
        self.chain          = abi.Uint16()   #: The Id of the chain where the message originated
        self.emitter        = abi.Address()  #: The address of the contract that emitted this message on the origin chain
        self.sequence       = abi.Uint64()   #: Unique integer representing the index, used for dedupe/ordering
        self.consistency    = abi.Uint8()    #

        self.type       = abi.Uint8()   #: Type of message
        self.amount     = abi.Address() #: amount of transfer
        self.contract   = abi.Address() #: asset transferred
        self.from_chain = abi.Uint16()  #: Id of the chain the token originated
        self.to_address = abi.Address() #: Receiver of the token transfer
        self.to_chain   = abi.Uint16()  #: Id of the chain where the token transfer should be redeemed
        self.fee        = abi.Address() #: Amount to pay relayer

        self.payload = abi.DynamicBytes()  #: Arbitrary byte payload
        # fmt: on

    def decode(self, vaa: Expr) -> Expr:
        return Seq(
            (offset := ScratchVar()).store(Int(0)),
            self.version.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.version),
            self.index.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.index),
            self.siglen.decode(vaa, start_index=offset.load()),
            # Increase offset to skip over sigs && digest
            offset.store(
                offset.load()
                + Int(self.siglen.type_spec().byte_length_static())
                + (self.siglen.get() * Int(66))
            ),
            self.timestamp.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.timestamp),
            self.nonce.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.nonce),
            self.chain.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.chain),
            self.emitter.decode(vaa, start_index=offset.load(), length=Int(32)),
            move_offset(offset, self.emitter),
            self.sequence.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.sequence),
            self.consistency.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.consistency),
            self.type.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.type),
            self.amount.decode(vaa, start_index=offset.load(), length=Int(32)),
            move_offset(offset, self.amount),
            self.contract.decode(vaa, start_index=offset.load(), length=Int(32)),
            move_offset(offset, self.contract),
            self.from_chain.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.from_chain),
            self.to_address.decode(vaa, start_index=offset.load(), length=Int(32)),
            move_offset(offset, self.to_address),
            self.to_chain.decode(vaa, start_index=offset.load()),
            move_offset(offset, self.to_chain),
            self.fee.decode(vaa, start_index=offset.load(), length=Int(32)),
            move_offset(offset, self.fee),
            self.payload.set(Suffix(vaa, offset.load())),
        )


class WormholeTransfer(Application, ABC):
    """ Wormhole Payload3 Message handler 
    
        A Message transfer from another chain to Algorand  using the Wormhole protocol 
        will cause this contract to have it's `portal_transfer` method called. 


    """

    @external
    def portal_transfer(
        self, vaa: abi.DynamicBytes, *, output: abi.DynamicBytes
    ) -> Expr:
        """ 
            portal_transfer accepts a VAA containing information about the transfer and the payload. 

            To allow a more flexible interface we publicize that we output generic bytes

        """

        return Seq(
            (ctvaa := ContractTransferVAA()).decode(vaa.get()),
            self.handle_transfer(ctvaa, output=output),
        )

    # Should be overridden with whatever app specific stuff
    # needs to be done on transfer
    @abstractclassmethod
    def handle_transfer(self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes) -> Expr:
        return  Reject()


if __name__ == "__main__":
    import json

    wht = WormholeTransfer()
    print(wht.approval_program)
    print(json.dumps(wht.contract.dictify()))
