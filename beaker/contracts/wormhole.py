from beaker.application import Application
from beaker.decorators import handler
from pyteal import (
    Assert,
    abi,
    Expr,
    Seq,
    ScratchVar,
    Int,
    TealType,
    Len,
    Suffix,
)


def move_offset(offset: ScratchVar, t: abi.BaseType) -> Expr:
    return offset.store(offset.load() + Int(t.type_spec().byte_length_static()))


class ContractTransferVAA:
    version: abi.Uint8  # Version of VAA
    index: abi.Uint32  #  Which guardian set to be validated against
    siglen: abi.Uint8  # How many signatures
    timestamp: abi.Uint32  # TS of message
    nonce: abi.Uint32  # Uniquifying
    chain: abi.Uint16  # The Id of the chain where the message originated
    emitter: abi.Address  # The address of the contract that emitted this message on the origin chain
    sequence: abi.Uint64  # Unique integer representing the index, used for dedupe/ordering
    consistency: abi.Uint8  #

    type: abi.Uint8  # Type of message
    amount: abi.Address  # amount of transfer
    contract: abi.Address  # asset transferred
    from_chain: abi.Uint16  # Id of the chain the token originated
    to_address: abi.Address  # Receiver of the token transfer
    to_chain: abi.Uint16  # Id of the chain where the token transfer should be redeemed
    fee: abi.Address  # Amount to pay relayer

    payload: ScratchVar  # Arbitrary byte payload

    def __init__(self):
        self.version = abi.Uint8()
        self.index = abi.Uint32()
        self.siglen = abi.Uint8()
        self.timestamp = abi.Uint32()
        self.nonce = abi.Uint32()
        self.chain = abi.Uint16()
        self.emitter = abi.Address()
        self.sequence = abi.Uint64()
        self.consistency = abi.Uint8()

        self.type = abi.Uint8()
        self.amount = abi.Address()
        self.contract = abi.Address()
        self.from_chain = abi.Uint16()
        self.to_address = abi.Address()
        self.to_chain = abi.Uint16()
        self.fee = abi.Address()

        self.payload = ScratchVar(TealType.bytes)

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
            self.payload.store(Suffix(vaa, offset.load())),
        )


class WormholeTransfer(Application):

    # Should be overridden with whatever app specific stuff
    # needs to be done on transfer
    def handle_transfer(self, ctvaa: ContractTransferVAA) -> Expr:
        return Assert(Len(ctvaa.payload.load()) > Int(0))

    @handler
    def portal_transfer(
        self, vaa: abi.DynamicArray[abi.Byte], *, output: abi.DynamicArray[abi.Byte]
    ) -> Expr:
        return Seq(
            (scratch := abi.String()).decode(vaa.encode()),
            (ctvaa := ContractTransferVAA()).decode(scratch.get()),
            self.handle_transfer(ctvaa),
            output.decode(ctvaa.payload.load()),
        )


if __name__ == "__main__":
    import json

    wht = WormholeTransfer()

    print(wht.approval_program)
    print(json.dumps(wht.contract.dictify()))
