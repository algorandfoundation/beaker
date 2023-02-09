import typing

from pyteal import (
    Assert,
    Expr,
    Global,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Pop,
    Seq,
    Suffix,
    TealType,
    TxnField,
    TxnType,
    abi,
)

from beaker import (
    Application,
    ApplicationStateValue,
    Authorize,
    consts,
    unconditional_create_approval,
)
from beaker.lib.storage import Mapping, List


# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


Affirmation = abi.StaticBytes[typing.Literal[64]]

BoxFlatMinBalance = 2500
BoxByteMinBalance = 400
AssetMinBalance = 100000


def axfer(
    asset_id: Expr,
    amount: Expr,
    receiver: Expr,
    extra: typing.Mapping[TxnField, Expr | list[Expr]] | None = None,
) -> dict[TxnField, Expr | list[Expr]]:
    base: dict[TxnField, Expr | list[Expr]] = {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.xfer_asset: asset_id,
        TxnField.asset_amount: amount,
        TxnField.asset_receiver: receiver,
    }
    return base | (extra or {})


def clawback_axfer(
    asset_id: Expr,
    amount: Expr,
    receiver: Expr,
    clawback_addr: Expr,
    extra: dict[TxnField, Expr | list[Expr]] | None = None,
) -> dict[TxnField, Expr | list[Expr]]:
    return axfer(
        asset_id,
        amount,
        receiver,
        (extra or {}) | {TxnField.asset_sender: clawback_addr},
    )


class MembershipClubState:
    membership_token = ApplicationStateValue(
        TealType.uint64,
        static=True,
        descr="The asset that represents membership of this club",
    )


####
# Box abstractions

# A Mapping will create a new box for every unique key,
# taking a data type for key and value
# Only static types can provide information about the max
# size (and min balance required).
membership_records = Mapping(abi.Address, MembershipRecord)

# A Listing is a simple list, initialized with some _static_ data type and a length
affirmations = List(Affirmation, 10, name="affirmations")

#####
# Math for determining min balance based on expected size of boxes
_max_members = 1000
_member_box_size = abi.size_of(MembershipRecord)
_min_balance = (
    AssetMinBalance  # Cover min bal for member token
    + (BoxFlatMinBalance + (_member_box_size * BoxByteMinBalance))
    * _max_members  # cover min bal for member record boxes we might create
    + (
        BoxFlatMinBalance + (affirmations._box_size * BoxByteMinBalance)
    )  # cover min bal for affirmation box
)
####

MaxMembers = Int(_max_members)
MinimumBalance = Int(_min_balance)


membership_club_app = Application(
    "MembershipClub", state=MembershipClubState
).implement(unconditional_create_approval)


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def bootstrap(
    seed: abi.PaymentTransaction,
    token_name: abi.String,
    *,
    output: abi.Uint64,
):
    """create membership token and receive initial seed payment"""
    return Seq(
        Assert(
            seed.get().receiver() == Global.current_application_address(),
            comment="payment must be to app address",
        ),
        Assert(
            seed.get().amount() >= MinimumBalance,
            comment=f"payment must be for >= {_min_balance}",
        ),
        Pop(affirmations.create()),
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset_name: token_name.get(),
                TxnField.config_asset_total: MaxMembers,
                TxnField.config_asset_default_frozen: Int(1),
                TxnField.config_asset_manager: Global.current_application_address(),
                TxnField.config_asset_clawback: Global.current_application_address(),
                TxnField.config_asset_freeze: Global.current_application_address(),
                TxnField.config_asset_reserve: Global.current_application_address(),
                TxnField.fee: Int(0),
            }
        ),
        membership_club_app.state.membership_token.set(InnerTxn.created_asset_id()),
        output.set(membership_club_app.state.membership_token),
    )


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def remove_member(member: abi.Address):
    return Pop(membership_records[member].delete())


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def add_member(
    new_member: abi.Account,
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
):
    return Seq(
        (role := abi.Uint8()).set(Int(0)),
        (voted := abi.Bool()).set(consts.FALSE),
        (mr := MembershipRecord()).set(role, voted),
        membership_records[new_member.address()].set(mr),
        InnerTxnBuilder.Execute(
            clawback_axfer(
                membership_club_app.state.membership_token,
                Int(1),
                new_member.address(),
                Global.current_application_address(),
                extra={TxnField.fee: Int(0)},
            )
        ),
    )


@membership_club_app.external()
def get_membership_record(member: abi.Address, *, output: MembershipRecord):
    return membership_records[member].store_into(output)


@membership_club_app.external(
    authorize=Authorize.holds_token(membership_club_app.state.membership_token)
)
def set_affirmation(
    idx: abi.Uint16,
    affirmation: Affirmation,
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
):
    return affirmations[idx.get()].set(affirmation)


@membership_club_app.external(
    authorize=Authorize.holds_token(membership_club_app.state.membership_token)
)
def get_affirmation(
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
    *,
    output: Affirmation,
):
    return output.set(affirmations[Global.round() % affirmations.elements])


class MemberState:
    club_app_id = ApplicationStateValue(TealType.uint64)
    last_affirmation = ApplicationStateValue(TealType.bytes)
    membership_token = ApplicationStateValue(TealType.uint64)


app_member_app = Application("AppMember", state=MemberState).implement(
    unconditional_create_approval
)


@app_member_app.external(
    authorize=Authorize.only(Global.creator_address()), name="bootstrap"
)
def app_member_bootstrap(
    seed: abi.PaymentTransaction,
    app_id: abi.Application,
    membership_token: abi.Asset,
):
    return Seq(
        # Set app id
        app_member_app.state.club_app_id.set(app_id.application_id()),
        # Set membership token
        app_member_app.state.membership_token.set(membership_token.asset_id()),
        # Opt in to membership token
        InnerTxnBuilder.Execute(
            axfer(
                membership_token.asset_id(),
                Int(0),
                Global.current_application_address(),
                extra={TxnField.fee: Int(0)},
            )
        ),
    )


@app_member_app.external(name="get_affirmation")
def app_member_get_affirmation(
    member_token: abi.Asset = app_member_app.state.membership_token,  # type: ignore[assignment]
    club_app: abi.Application = app_member_app.state.club_app_id,  # type: ignore[assignment]
):

    return Seq(
        InnerTxnBuilder.ExecuteMethodCall(
            app_id=app_member_app.state.club_app_id,
            method_signature=membership_club_app.abi_methods[
                "get_affirmation"
            ].method_signature(),
            args=[member_token],
        ),
        app_member_app.state.last_affirmation.set(Suffix(InnerTxn.last_log(), Int(4))),
    )
