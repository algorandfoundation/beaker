from pyteal import Bytes, Expr, JsonRef, ScratchVar, Seq, TealType, abi

from beaker import (
    Application,
    ReservedGlobalStateValue,
    unconditional_create_approval,
)
from examples.wormhole.wormhole import ContractTransferVAA, wormhole_transfer


class OracleData(abi.NamedTuple):
    timestamp: abi.Field[abi.Uint64]
    price: abi.Field[abi.Uint64]
    confidence: abi.Field[abi.Uint64]


class OracleState:
    prices = ReservedGlobalStateValue(stack_type=TealType.bytes, max_keys=64)


oracle_data_cache_app = Application(
    "OracleDataCache",
    descr="""
    Stores price feed in application state keyed by timestamp

    TODO: more than 64 vals lol
    """,
    state=OracleState(),
    include=[unconditional_create_approval],
)


@oracle_data_cache_app.external
def lookup(ts: abi.Uint64, *, output: OracleData) -> Expr:
    return output.decode(oracle_data_cache_app.state.prices[ts].get_must())


def handle_transfer(ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes) -> Expr:
    """
    invoked from parent class `portal_transfer` after parsing the VAA into
    abi vars
    """
    return Seq(
        # TODO: assert foreign sender? Should be in provided contract?
        # Do this once, since `get`` incurs a couple op penalty over `load`
        (payload := ScratchVar()).store(ctvaa.payload.get()),
        # Read vals from json
        (timestamp := abi.Uint64()).set(JsonRef.as_uint64(payload.load(), Bytes("ts"))),
        (price := abi.Uint64()).set(JsonRef.as_uint64(payload.load(), Bytes("price"))),
        (confidence := abi.Uint64()).set(
            JsonRef.as_uint64(payload.load(), Bytes("confidence"))
        ),
        # Construct named tuple for storage
        (od := abi.make(OracleData)).set(timestamp, price, confidence),
        # Write to app state
        oracle_data_cache_app.state.prices[timestamp].set(od.encode()),
        # echo the payload
        output.set(ctvaa.payload),
    )


oracle_data_cache_app.include(wormhole_transfer, handle_transfer=handle_transfer)


if __name__ == "__main__":
    oracle_data_cache_app.build().export("./spec")
