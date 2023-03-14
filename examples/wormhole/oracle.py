import pyteal as pt

import beaker

from examples.wormhole import wormhole


class OracleData(pt.abi.NamedTuple):
    timestamp: pt.abi.Field[pt.abi.Uint64]
    price: pt.abi.Field[pt.abi.Uint64]
    confidence: pt.abi.Field[pt.abi.Uint64]


class State:
    prices = beaker.ReservedGlobalStateValue(stack_type=pt.TealType.bytes, max_keys=64)


app = beaker.Application(
    "OracleDataCache",
    descr="Stores price feed in application state keyed by timestamp",
    state=State(),
)


@app.external
def lookup(ts: pt.abi.Uint64, *, output: OracleData) -> pt.Expr:
    return output.decode(app.state.prices[ts].get_must())


class MyStrategy(wormhole.WormholeStrategy):
    def handle_transfer(
        self,
        ctvaa: wormhole.ContractTransferVAA,
        *,
        output: pt.abi.DynamicBytes,
    ) -> pt.Expr:
        """
        invoked from blueprint method `portal_transfer` after parsing the VAA into
        abi vars
        """
        return pt.Seq(
            # TODO: assert foreign sender? Should be in provided contract?
            # Do this once, since `get`` incurs a couple op penalty over `load`
            (payload := pt.ScratchVar()).store(ctvaa.payload.get()),
            # Read vals from json
            (timestamp := pt.abi.Uint64()).set(
                pt.JsonRef.as_uint64(payload.load(), pt.Bytes("ts"))
            ),
            (price := pt.abi.Uint64()).set(
                pt.JsonRef.as_uint64(payload.load(), pt.Bytes("price"))
            ),
            (confidence := pt.abi.Uint64()).set(
                pt.JsonRef.as_uint64(payload.load(), pt.Bytes("confidence"))
            ),
            # Construct named tuple for storage
            (od := pt.abi.make(OracleData)).set(timestamp, price, confidence),
            # Write to app state
            app.state.prices[timestamp].set(od.encode()),
            # echo the payload
            output.set(ctvaa.payload),
        )


app.apply(wormhole.wormhole_transfer, strategy=MyStrategy())
