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
    GlobalStateValue,
    Authorize,
    consts,
    unconditional_create_approval,
)
from beaker.consts import BOX_BYTE_MIN_BALANCE, BOX_FLAT_MIN_BALANCE, ASSET_MIN_BALANCE
from beaker.lib.storage import BoxMapping, BoxList


# NamedTuple we'll store in a box per member
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


# Custom type alias
Affirmation = abi.StaticBytes[typing.Literal[64]]


class MembershipClubState:
    membership_token = GlobalStateValue(
        TealType.uint64,
        static=True,
        descr="The asset that represents membership of this club",
    )

    # A Listing is a simple list, initialized with some _static_ data type and a length
    affirmations = BoxList(Affirmation, 10)

    def __init__(self, *, max_members: int, record_type: type[abi.BaseType]):
        self.record_type = record_type
        # A Mapping will create a new box for every unique key,
        # taking a data type for key and value
        # Only static types can provide information about the max
        # size (and thus min balance required) - dynamic types will fail at abi.size_of
        self.membership_records = BoxMapping(abi.Address, record_type)

        # Math for determining min balance based on expected size of boxes
        self.max_members = Int(max_members)
        self.minimum_balance = Int(
            ASSET_MIN_BALANCE  # Cover min bal for member token
            + (BOX_FLAT_MIN_BALANCE + (abi.size_of(record_type) * BOX_BYTE_MIN_BALANCE))
            * max_members  # cover min bal for member record boxes we might create
            + (
                BOX_FLAT_MIN_BALANCE
                + (self.affirmations.box_size.value * BOX_BYTE_MIN_BALANCE)
            )  # cover min bal for affirmation box
        )


membership_club_app = Application(
    "MembershipClub",
    state=MembershipClubState(max_members=1000, record_type=MembershipRecord),
)


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def bootstrap(
    seed: abi.PaymentTransaction,
    token_name: abi.String,
    *,
    output: abi.Uint64,
) -> Expr:
    """create membership token and receive initial seed payment"""
    return Seq(
        Assert(
            seed.get().receiver() == Global.current_application_address(),
            comment="payment must be to app address",
        ),
        Assert(
            seed.get().amount() >= membership_club_app.state.minimum_balance,
            comment=f"payment must be for >= {membership_club_app.state.minimum_balance.value}",
        ),
        Pop(membership_club_app.state.affirmations.create()),
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset_name: token_name.get(),
                TxnField.config_asset_total: membership_club_app.state.max_members,
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
def remove_member(member: abi.Address) -> Expr:
    return Pop(membership_club_app.state.membership_records[member].delete())


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def add_member(
    new_member: abi.Account,
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
) -> Expr:
    return Seq(
        (role := abi.Uint8()).set(Int(0)),
        (voted := abi.Bool()).set(consts.FALSE),
        (mr := MembershipRecord()).set(role, voted),
        membership_club_app.state.membership_records[new_member.address()].set(mr),
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


@membership_club_app.external(authorize=Authorize.only(Global.creator_address()))
def update_role(member: abi.Account, new_role: abi.Uint8) -> Expr:
    return Seq(
        (mr := MembershipRecord()).decode(
            membership_club_app.state.membership_records[member.address()].get()
        ),
        # retain their voted status
        (voted := abi.Bool()).set(mr.voted),
        mr.set(new_role, voted),
        membership_club_app.state.membership_records[member.address()].set(mr),
    )


@membership_club_app.external()
def get_membership_record(member: abi.Address, *, output: MembershipRecord) -> Expr:
    return membership_club_app.state.membership_records[member].store_into(output)


@membership_club_app.external(
    authorize=Authorize.holds_token(membership_club_app.state.membership_token)
)
def set_affirmation(
    idx: abi.Uint16,
    affirmation: Affirmation,
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
) -> Expr:
    return membership_club_app.state.affirmations[idx.get()].set(affirmation)


@membership_club_app.external(
    authorize=Authorize.holds_token(membership_club_app.state.membership_token)
)
def get_affirmation(
    membership_token: abi.Asset = membership_club_app.state.membership_token,  # type: ignore[assignment]
    *,
    output: Affirmation,
) -> Expr:
    return output.set(
        membership_club_app.state.affirmations[
            Global.round() % membership_club_app.state.affirmations.elements
        ]
    )


class MemberState:
    club_app_id = GlobalStateValue(TealType.uint64)
    last_affirmation = GlobalStateValue(TealType.bytes)
    membership_token = GlobalStateValue(TealType.uint64)


app_member_app = Application("AppMember", state=MemberState()).implement(
    unconditional_create_approval
)


@app_member_app.external(
    authorize=Authorize.only(Global.creator_address()), name="bootstrap"
)
def app_member_bootstrap(
    seed: abi.PaymentTransaction,
    app_id: abi.Application,
    membership_token: abi.Asset,
) -> Expr:
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
) -> Expr:
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


# Utility functions
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
