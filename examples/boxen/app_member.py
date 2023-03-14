import pyteal as pt

import beaker

from examples.boxen import membership_club


class MemberState:
    club_app_id = beaker.GlobalStateValue(pt.TealType.uint64)
    last_affirmation = beaker.GlobalStateValue(pt.TealType.bytes)
    membership_token = beaker.GlobalStateValue(pt.TealType.uint64)


app = beaker.Application(
    "AppMember",
    state=MemberState(),
    build_options=beaker.BuildOptions(scratch_slots=False),
)


@app.external(authorize=beaker.Authorize.only_creator())
def bootstrap(
    seed: pt.abi.PaymentTransaction,
    app_id: pt.abi.Application,
    membership_token: pt.abi.Asset,
) -> pt.Expr:
    return pt.Seq(
        # Set app id
        app.state.club_app_id.set(app_id.application_id()),
        # Set membership token
        app.state.membership_token.set(membership_token.asset_id()),
        # Opt in to membership token
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.xfer_asset: membership_token.asset_id(),
                pt.TxnField.asset_amount: pt.Int(0),
                pt.TxnField.asset_receiver: pt.Global.current_application_address(),
                pt.TxnField.fee: pt.Int(0),
            }
        ),
    )


@app.external
def get_affirmation(
    member_token: pt.abi.Asset = app.state.membership_token,  # type: ignore[assignment]
    club_app: pt.abi.Application = app.state.club_app_id,  # type: ignore[assignment]
) -> pt.Expr:
    return pt.Seq(
        pt.InnerTxnBuilder.ExecuteMethodCall(
            app_id=app.state.club_app_id,
            method_signature=membership_club.get_affirmation.method_signature(),
            args=[member_token],
        ),
        app.state.last_affirmation.set(pt.Suffix(pt.InnerTxn.last_log(), pt.Int(4))),
    )
