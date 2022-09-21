from abc import ABC, abstractmethod
from typing import Literal

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


def read_next(vaa: Expr, offset: int, t: abi.BaseType) -> tuple[int, Expr]:
    size = t.type_spec().byte_length_static()
    return offset + size, t.decode(vaa, start_index=Int(offset), length=Int(size))


Bytes32 = abi.StaticBytes[Literal[32]]


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
        self.amount = abi.make(Bytes32)
        #: asset transferred
        self.contract = abi.make(Bytes32)
        #: Id of the chain the token originated
        self.from_chain = abi.Uint16()
        #: Receiver of the token transfer
        self.to_address = abi.Address()
        #: Id of the chain where the token transfer should be redeemed
        self.to_chain = abi.Uint16()
        #: Amount to pay relayer
        self.fee = abi.make(Bytes32)
        #: Address that sent the transfer
        self.from_address = abi.Address()

        #: Arbitrary byte payload
        self.payload = abi.DynamicBytes()

    def decode(self, vaa: Expr) -> Expr:
        offset = 0
        ops: list[Expr] = []

        offset, e = read_next(vaa, offset, self.version)
        ops.append(e)

        offset, e = read_next(vaa, offset, self.index)
        ops.append(e)

        offset, e = read_next(vaa, offset, self.siglen)
        ops.append(e)

        # Increase offset to skip over sigs && digest
        # since these should be checked by the wormhole core contract
        ops.append(
            (digest_vaa := ScratchVar()).store(
                Suffix(vaa, Int(offset) + (self.siglen.get() * Int(66)))
            )
        )

        # Reset the offset now that we have const length elements
        offset = 0
        offset, e = read_next(digest_vaa.load(), offset, self.timestamp)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.nonce)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.chain)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.emitter)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.sequence)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.consistency)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.type)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.amount)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.contract)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.from_chain)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.to_address)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.to_chain)
        ops.append(e)
        offset, e = read_next(digest_vaa.load(), offset, self.from_address)
        ops.append(e)
        # Rest is payload
        ops.append(self.payload.set(Suffix(digest_vaa.load(), Int(offset))))

        return Seq(*ops)


class WormholeTransfer(Application, ABC):
    """Wormhole Payload3 Message handler

    A Message transfer from another chain to Algorand  using the Wormhole protocol
    will cause this contract to have it's `portal_transfer` method called.
    """

    @external
    def portal_transfer(
        self, vaa: abi.DynamicBytes, *, output: abi.DynamicBytes
    ) -> Expr:
        """portal_transfer accepts a VAA containing information about the transfer and the payload.

        Args:
            vaa: VAA encoded dynamic byte array

        Returns:
            Undefined byte array

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
        """handle transfer should be overridden with app specific logic
        needs to be done on transfer

        Args:
            ctvaa: The decoded ContractTransferVAA

        Returns:
            app specific byte array
        """
        return Reject()
