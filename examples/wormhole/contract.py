from typing import Final
from pyteal import *
from beaker import *

if __name__ == "__main__":
    from wormhole import ContractTransferVAA, WormholeTransfer
else:
    from .wormhole import ContractTransferVAA, WormholeTransfer


class OracleDataCache(WormholeTransfer):
    """
    Stores price feed in application state keyed by timestamp

    TODO: more than 64 vals lol
    """

    class OracleData(abi.NamedTuple):
        timestamp: abi.Field[abi.Uint64]
        price: abi.Field[abi.Uint64]
        confidence: abi.Field[abi.Uint64]

    prices: Final[ReservedApplicationStateValue] = ReservedApplicationStateValue(
        stack_type=TealType.bytes, max_keys=64
    )

    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes
    ) -> Expr:
        """
        invoked from parent class `portal_transfer` after parsing the VAA into
        abi vars
        """
        return Seq(
            # TODO: assert foreign sender? Should be in provided contract?
            # Do this once, since `get`` incurs a couple op penalty over `load`
            (payload := ScratchVar()).store(ctvaa.payload.get()),
            # Read vals from json
            (timestamp := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("ts"))
            ),
            (price := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("price"))
            ),
            (confidence := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("confidence"))
            ),
            # Construct named tuple for storage
            (od := abi.make(OracleDataCache.OracleData)).set(
                timestamp, price, confidence
            ),
            # Write to app state
            self.prices[timestamp].set(od.encode()),
            # echo the payload
            output.set(ctvaa.payload),
        )

    @external
    def lookup(self, ts: abi.Uint64, *, output: OracleData):
        return output.decode(self.prices[ts].get_must())


if __name__ == "__main__":
    OracleDataCache().dump("./spec")
