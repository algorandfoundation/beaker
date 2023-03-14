import abc
from typing import Literal

import pyteal as pt

import beaker

Bytes32 = pt.abi.StaticBytes[Literal[32]]


class ContractTransferVAA:
    def __init__(self) -> None:
        #: Version of VAA
        self.version = pt.abi.Uint8()
        #: Which guardian set to be validated against
        self.index = pt.abi.Uint32()
        #: How many signatures
        self.siglen = pt.abi.Uint8()
        #: TS of message
        self.timestamp = pt.abi.Uint32()
        #: Uniquifying
        self.nonce = pt.abi.Uint32()
        #: The Id of the chain where the message originated
        self.chain = pt.abi.Uint16()
        #: The address of the contract that emitted this message on the origin chain
        self.emitter = pt.abi.Address()
        #: Unique integer representing the index, used for dedupe/ordering
        self.sequence = pt.abi.Uint64()

        self.consistency = pt.abi.Uint8()  # ?

        #: Type of message
        self.type = pt.abi.Uint8()
        #: amount of transfer
        self.amount = pt.abi.make(Bytes32)
        #: asset transferred
        self.contract = pt.abi.make(Bytes32)
        #: Id of the chain the token originated
        self.from_chain = pt.abi.Uint16()
        #: Receiver of the token transfer
        self.to_address = pt.abi.Address()
        #: Id of the chain where the token transfer should be redeemed
        self.to_chain = pt.abi.Uint16()
        #: Amount to pay relayer
        self.fee = pt.abi.make(Bytes32)
        #: Address that sent the transfer
        self.from_address = pt.abi.Address()

        #: Arbitrary byte payload
        self.payload = pt.abi.DynamicBytes()

    def decode(self, vaa: pt.Expr) -> pt.Expr:
        offset = 0
        ops: list[pt.Expr] = []

        offset, e = _read_next(vaa, offset, self.version)
        ops.append(e)

        offset, e = _read_next(vaa, offset, self.index)
        ops.append(e)

        offset, e = _read_next(vaa, offset, self.siglen)
        ops.append(e)

        # Increase offset to skip over sigs && digest
        # since these should be checked by the wormhole core contract
        ops.append(
            (digest_vaa := pt.ScratchVar()).store(
                pt.Suffix(vaa, pt.Int(offset) + (self.siglen.get() * pt.Int(66)))
            )
        )

        # Reset the offset now that we have const length elements
        offset = 0
        offset, e = _read_next(digest_vaa.load(), offset, self.timestamp)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.nonce)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.chain)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.emitter)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.sequence)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.consistency)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.type)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.amount)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.contract)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.from_chain)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.to_address)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.to_chain)
        ops.append(e)
        offset, e = _read_next(digest_vaa.load(), offset, self.from_address)
        ops.append(e)
        # Rest is payload
        ops.append(self.payload.set(pt.Suffix(digest_vaa.load(), pt.Int(offset))))

        return pt.Seq(*ops)


def _read_next(vaa: pt.Expr, offset: int, t: pt.abi.BaseType) -> tuple[int, pt.Expr]:
    size = t.type_spec().byte_length_static()
    return offset + size, t.decode(vaa, start_index=pt.Int(offset), length=pt.Int(size))


class WormholeStrategy(abc.ABC):
    @abc.abstractmethod
    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: pt.abi.DynamicBytes
    ) -> pt.Expr:
        ...


def wormhole_transfer(
    app: beaker.Application,
    strategy: WormholeStrategy,
) -> None:
    """Implement Wormhole Payload3 Message handler

    A Message transfer from another chain to Algorand  using the Wormhole protocol
    will cause this contract to have it's `portal_transfer` method called.

    Args:
        app: app to add to
        strategy: app specific logic that needs to be done on transfer
    """

    @app.external
    def portal_transfer(
        vaa: pt.abi.DynamicBytes, *, output: pt.abi.DynamicBytes
    ) -> pt.Expr:
        """portal_transfer accepts a VAA containing information about the transfer
        and the payload.

        Args:
            vaa: VAA encoded dynamic byte array

        Returns:
            Undefined byte array

        To allow a more flexible interface we publicize that we output generic bytes
        """
        return pt.Seq(
            (ctvaa := ContractTransferVAA()).decode(vaa.get()),
            strategy.handle_transfer(ctvaa, output=output),
        )
