from typing import Final
from pyteal import *
from beaker import *
from beaker.contracts.wormhole import ContractTransferVAA, WormholeTransfer


class OracleDataCache(WormholeTransfer):
    class OracleData(abi.NamedTuple):
        timestamp: abi.Field[abi.Uint64]
        price: abi.Field[abi.Uint64]
        confidence: abi.Field[abi.Uint64]

    prices: Final[DynamicApplicationStateValue] = DynamicApplicationStateValue(
        stack_type=TealType.bytes, max_keys=64
    )

    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes
    ) -> Expr:
        return Seq(
            # TODO: assert foreign sender?
            (payload := ScratchVar()).store(ctvaa.payload.get()),
            (timestamp := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("ts"))
            ),
            (price := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("price"))
            ),
            (confidence := abi.Uint64()).set(
                JsonRef.as_uint64(payload.load(), Bytes("confidence"))
            ),
            (od := abi.make(OracleDataCache.OracleData)).set(
                timestamp, price, confidence
            ),
            self.prices[timestamp].set(od.encode()),
            # echo the payload
            output.set(ctvaa.payload),
        )

    @external
    def lookup(self, ts: abi.Uint64, *, output: OracleData):
        return output.decode(self.prices[ts].get_must())
