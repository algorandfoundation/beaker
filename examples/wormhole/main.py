from typing import Final
from pyteal import *
from beaker import *
from beaker.contracts.wormhole import ContractTransferVAA, WormholeTransfer


class OracleData(abi.NamedTuple):
    timestamp: abi.Field[abi.Uint64]
    price: abi.Field[abi.Uint64]
    confidence: abi.Field[abi.Uint64]


class OraclePayload:
    def __init__(self):
        self.timestamp = abi.Uint64()
        self.price = abi.Uint64()
        self.confidence = abi.Uint64()

    def decode_msg(self, payload: Expr):
        return Seq(
            self.timestamp.set(JsonRef.as_uint64(payload, Bytes("ts"))),
            self.price.set(JsonRef.as_uint64(payload, Bytes("price"))),
            self.confidence.set(JsonRef.as_uint64(payload, Bytes("confidence"))),
        )

    def encode(self) -> Expr:
        return Seq(
            (od := OracleData()).set(self.timestamp, self.price, self.confidence),
            od.encode(),
        )


class OracleDataCache(WormholeTransfer):
    prices: Final[DynamicApplicationStateValue] = DynamicApplicationStateValue(
        stack_type=TealType.bytes, max_keys=64
    )

    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes
    ) -> Expr:
        return Seq(
            # TODO: assert foreign sender?
            # (op := OraclePayload()).decode_msg(ctvaa.payload.get()),
            # self.prices[op.timestamp].set(op.encode()),
            # don't return anything
            output.set(ctvaa.payload.get()),
        )

    @external
    def lookup(self, ts: abi.Uint64, *, output: OracleData):
        return output.decode(self.prices[ts].get_must())


def demo():

    base_vaa = bytes.fromhex(
        "010000000001008049340af360a47103a962108cb57b9deebcc99e8e6ddeca1a"
        + "1fb025413a62ac2cae4abd6b7e0ce7fc5a6bc99536387a3827cbbb0c710c81213"
        + "a417cb59b89de01630d06ae0000000000088edf5b0e108c3a1a0a4b704cc89591"
        + "f2ad8d50df24e991567e640ed720a94be20000000000000004000300000000000"
        + "00000000000000000000000000000000000000000000000000064000000000000"
        + "0000000000000000000000000000000000000000000000000000000f6463fab1a"
        + "45027a3c70781ae588e4e6661d21a7c19535a5d6b4f4c3164a13be1000f0b7ef3"
        + "fcf3f8d9efc458695dc7bd7e534080ac7b48f2b881fd3063b1308f0648"
    )

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        OracleDataCache(),
        signer=sandbox.get_accounts().pop().signer,
    )

    app_client.create()

    result = app_client.call(OracleDataCache.portal_transfer, vaa=base_vaa + b"hi ben")
    result_bytes: bytes = bytes(result.return_value)
    print(result_bytes.decode("utf-8"))


if __name__ == "__main__":
    demo()
