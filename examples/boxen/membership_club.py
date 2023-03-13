import typing

import pyteal as pt

import beaker
from beaker.consts import (
    ASSET_MIN_BALANCE,
    BOX_BYTE_MIN_BALANCE,
    BOX_FLAT_MIN_BALANCE,
    FALSE,
)
from beaker.lib.storage import BoxList, BoxMapping


# NamedTuple we'll store in a box per member
class MembershipRecord(pt.abi.NamedTuple):
    role: pt.abi.Field[pt.abi.Uint8]
    voted: pt.abi.Field[pt.abi.Bool]


# Custom type alias
Affirmation = pt.abi.StaticBytes[typing.Literal[64]]


class MembershipClubState:
    membership_token = beaker.GlobalStateValue(
        pt.TealType.uint64,
        static=True,
        descr="The asset that represents membership of this club",
    )

    # A Listing is a simple list, initialized with some _static_ data type and a length
    affirmations = BoxList(Affirmation, 10)

    def __init__(self, *, max_members: int, record_type: type[pt.abi.BaseType]):
        self.record_type = record_type
        # A Mapping will create a new box for every unique key,
        # taking a data type for key and value
        # Only static types can provide information about the max
        # size (and thus min balance required) - dynamic types will fail at abi.size_of
        self.membership_records = BoxMapping(pt.abi.Address, record_type)

        # Math for determining min balance based on expected size of boxes
        self.max_members = pt.Int(max_members)
        self.minimum_balance = pt.Int(
            ASSET_MIN_BALANCE  # Cover min bal for member token
            + (
                BOX_FLAT_MIN_BALANCE
                + (pt.abi.size_of(record_type) * BOX_BYTE_MIN_BALANCE)
            )
            * max_members  # cover min bal for member record boxes we might create
            + (
                BOX_FLAT_MIN_BALANCE
                + (self.affirmations.box_size.value * BOX_BYTE_MIN_BALANCE)
            )  # cover min bal for affirmation box
        )


app = beaker.Application(
    "MembershipClub",
    state=MembershipClubState(max_members=1000, record_type=MembershipRecord),
    build_options=beaker.BuildOptions(scratch_slots=False),
)


@app.external(authorize=beaker.Authorize.only_creator())
def bootstrap(
    seed: pt.abi.PaymentTransaction,
    token_name: pt.abi.String,
    *,
    output: pt.abi.Uint64,
) -> pt.Expr:
    """create membership token and receive initial seed payment"""
    return pt.Seq(
        pt.Assert(
            seed.get().receiver() == pt.Global.current_application_address(),
            comment="payment must be to app address",
        ),
        pt.Assert(
            seed.get().amount() >= app.state.minimum_balance,
            comment=f"payment must be for >= {app.state.minimum_balance.value}",
        ),
        pt.Pop(app.state.affirmations.create()),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetConfig,
                pt.TxnField.config_asset_name: token_name.get(),
                pt.TxnField.config_asset_total: app.state.max_members,
                pt.TxnField.config_asset_default_frozen: pt.Int(1),
                pt.TxnField.config_asset_manager: pt.Global.current_application_address(),
                pt.TxnField.config_asset_clawback: pt.Global.current_application_address(),
                pt.TxnField.config_asset_freeze: pt.Global.current_application_address(),
                pt.TxnField.config_asset_reserve: pt.Global.current_application_address(),
                pt.TxnField.fee: pt.Int(0),
            }
        ),
        app.state.membership_token.set(pt.InnerTxn.created_asset_id()),
        output.set(app.state.membership_token),
    )


@app.external(authorize=beaker.Authorize.only_creator())
def remove_member(member: pt.abi.Address) -> pt.Expr:
    return pt.Pop(app.state.membership_records[member].delete())


@app.external(authorize=beaker.Authorize.only_creator())
def add_member(
    new_member: pt.abi.Account,
    membership_token: pt.abi.Asset = app.state.membership_token,  # type: ignore[assignment]
) -> pt.Expr:
    return pt.Seq(
        (role := pt.abi.Uint8()).set(pt.Int(0)),
        (voted := pt.abi.Bool()).set(FALSE),
        (mr := MembershipRecord()).set(role, voted),
        app.state.membership_records[new_member.address()].set(mr),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.xfer_asset: app.state.membership_token,
                pt.TxnField.asset_amount: pt.Int(1),
                pt.TxnField.asset_receiver: new_member.address(),
                pt.TxnField.fee: pt.Int(0),
                pt.TxnField.asset_sender: pt.Global.current_application_address(),
            }
        ),
    )


@app.external(authorize=beaker.Authorize.only_creator())
def update_role(member: pt.abi.Account, new_role: pt.abi.Uint8) -> pt.Expr:
    return pt.Seq(
        (mr := MembershipRecord()).decode(
            app.state.membership_records[member.address()].get()
        ),
        # retain their voted status
        (voted := pt.abi.Bool()).set(mr.voted),
        mr.set(new_role, voted),
        app.state.membership_records[member.address()].set(mr),
    )


@app.external
def get_membership_record(
    member: pt.abi.Address, *, output: MembershipRecord
) -> pt.Expr:
    return app.state.membership_records[member].store_into(output)


@app.external(authorize=beaker.Authorize.holds_token(app.state.membership_token))
def set_affirmation(
    idx: pt.abi.Uint16,
    affirmation: Affirmation,
    membership_token: pt.abi.Asset = app.state.membership_token,  # type: ignore[assignment]
) -> pt.Expr:
    return app.state.affirmations[idx.get()].set(affirmation)


@app.external(authorize=beaker.Authorize.holds_token(app.state.membership_token))
def get_affirmation(
    membership_token: pt.abi.Asset = app.state.membership_token,  # type: ignore[assignment]
    *,
    output: Affirmation,
) -> pt.Expr:
    return output.set(
        app.state.affirmations[pt.Global.round() % app.state.affirmations.elements]
    )
