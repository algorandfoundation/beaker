from abc import ABC, abstractmethod
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


def read_next(vaa: Expr, offset: ScratchVar, t: abi.BaseType) -> Expr:
    size = Int(t.type_spec().byte_length_static())
    return Seq(
        t.decode(vaa, start_index=offset.load(), length=size),
        offset.store(offset.load() + size),
    )


class ContractTransferVAA:
    def __init__(self):
        #: Version of VAA
        self.version = abi.Uint8()
        #: Which guardian set to be validated against
        self.index = abi.Uint32()
        #: How many signatures
        self.siglen = abi.Uint8()
        #: TS of message
        self.timestamp = abi.Uint32()
        #: Uniquifying
        self.nonce = abi.Uint32()
        #: The Id of the chain where the message originated
        self.chain = abi.Uint16()
        #: The address of the contract that emitted this message on the origin chain
        self.emitter = abi.Address()
        #: Unique integer representing the index, used for dedupe/ordering
        self.sequence = abi.Uint64()

        self.consistency = abi.Uint8()  # ?

        #: Type of message
        self.type = abi.Uint8()
        #: amount of transfer
        self.amount = abi.Address()
        #: asset transferred
        self.contract = abi.Address()
        #: Id of the chain the token originated
        self.from_chain = abi.Uint16()
        #: Receiver of the token transfer
        self.to_address = abi.Address()
        #: Id of the chain where the token transfer should be redeemed
        self.to_chain = abi.Uint16()
        #: Amount to pay relayer
        self.fee = abi.Address()
        #: Address that sent the transfer
        self.from_address = abi.Address()

        #: Arbitrary byte payload
        self.payload = abi.DynamicBytes()

    def decode(self, vaa: Expr) -> Expr:
        return Seq(
            (offset := ScratchVar()).store(Int(0)),
            read_next(vaa, offset, self.version),
            read_next(vaa, offset, self.index),
            read_next(vaa, offset, self.siglen),
            # Increase offset to skip over sigs && digest
            # since these should be checked by the wormhole core contract
            offset.store(offset.load() + (self.siglen.get() * Int(66))),
            read_next(vaa, offset, self.timestamp),
            read_next(vaa, offset, self.nonce),
            read_next(vaa, offset, self.chain),
            read_next(vaa, offset, self.emitter),
            read_next(vaa, offset, self.sequence),
            read_next(vaa, offset, self.consistency),
            read_next(vaa, offset, self.type),
            read_next(vaa, offset, self.amount),
            read_next(vaa, offset, self.contract),
            read_next(vaa, offset, self.from_chain),
            read_next(vaa, offset, self.to_address),
            read_next(vaa, offset, self.to_chain),
            # read_next(vaa, offset, self.fee),
            read_next(vaa, offset, self.from_address),
            # Rest is payload
            self.payload.set(Suffix(vaa, offset.load())),
        )


class WormholeTransfer(Application, ABC):
    """Wormhole Payload3 Message handler

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

    @abstractmethod
    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes
    ) -> Expr:
        """

        Should be overridden with whatever app specific stuff
        needs to be done on transfer

        """
        return Reject()
