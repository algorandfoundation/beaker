from feature_gates import FeatureGates  # type: ignore

FeatureGates.set_sourcemap_enabled(True)  # noqa

from algosdk.encoding import decode_address  # noqa
import pyteal as pt  # noqa
from beaker import Application, sandbox, client, BuildOptions  # noqa
from beaker.lib.storage import BoxMapping  # noqa


class BoxExprState:
    m = BoxMapping(pt.abi.Address, pt.abi.Uint64)


app = Application(
    "boxexpr",
    state=BoxExprState,
    build_options=BuildOptions(
        frame_pointers=True, with_sourcemaps=True, annotate_teal=True
    ),
)


@app.external
def makeit() -> pt.Expr:
    return app.state.m[pt.Txn.sender()].set(pt.Itob(pt.Int(0)))


@app.external
def doit() -> pt.Expr:
    current_vote_tally = pt.Btoi(app.state.m[pt.Txn.sender()].get())
    new_vote_tally = pt.Add(current_vote_tally, pt.Int(1))
    # new_vote_tally is an Expr with deferred evaluation of the value
    # on `set` the mapping object will first Delete the box then try to BoxPut
    # but BoxPut will fail since new_vote_tally Expression tries to _get_ the value from
    # the box that was just deleted.
    return app.state.m[pt.Txn.sender()].set(pt.Itob(new_vote_tally))


if __name__ == "__main__":
    acct = sandbox.get_accounts().pop()
    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        app,
        signer=acct.signer,
    )

    app_client.create()
    app_client.fund(int(1e7))
    app_client.call(makeit, boxes=[(0, decode_address(acct.address))])
    app_client.call(doit, boxes=[(0, decode_address(acct.address))])
