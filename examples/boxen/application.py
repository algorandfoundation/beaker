from typing import Literal
from pyteal import *
from beaker import *

from beaker.application import get_method_signature
from beaker.lib.storage import Mapping, List

# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


Affirmation = abi.StaticBytes[Literal[64]]

BoxFlatMinBalance = 2500
BoxByteMinBalance = 400
AssetMinBalance = 100000


def axfer(
    asset_id: Expr,
    amount: Expr,
    receiver: Expr,
    extra: dict[TxnField, Expr] | None = None,
) -> dict[TxnField, Expr]:
    extra = extra if extra is not None else {}
    return {
        TxnField.type_enum: TxnType.AssetTransfer,
        TxnField.xfer_asset: asset_id,
        TxnField.asset_amount: amount,
        TxnField.asset_receiver: receiver,
    } | extra


def clawback_axfer(
    asset_id: Expr,
    amount: Expr,
    receiver: Expr,
    clawback_addr: Expr,
    extra: dict[TxnField, Expr] | None = None,
) -> dict[TxnField, Expr]:
    return axfer(asset_id, amount, receiver, extra) | {
        TxnField.asset_sender: clawback_addr,
    }


class MembershipClub(Application):
    ####
    # Box abstractions

    # A Mapping will create a new box for every unique key, taking a data type for key and value
    # Only static types can provide information about the max size (and min balance required).
    membership_records = Mapping(abi.Address, MembershipRecord)

    # A Listing is a simple list, initialized with some _static_ data type and a length
    affirmations = List(Affirmation, 10)

    #####
    # State vars

    membership_token = ApplicationStateValue(
        TealType.uint64,
        static=True,
        descr="The asset that represents membership of this club",
    )

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

    @external(authorize=Authorize.only(Global.creator_address()))
    def bootstrap(
        self,
        seed: abi.PaymentTransaction,
        token_name: abi.String,
        *,
        output: abi.Uint64,
    ):
        """create membership token and receive initial seed payment"""
        return Seq(
            Assert(
                seed.get().receiver() == self.address,
                comment="payment must be to app address",
            ),
            Assert(
                seed.get().amount() >= self.MinimumBalance,
                comment=f"payment must be for >= {self._min_balance}",
            ),
            Pop(self.affirmations.create()),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: token_name.get(),
                    TxnField.config_asset_total: self.MaxMembers,
                    TxnField.config_asset_default_frozen: Int(1),
                    TxnField.config_asset_manager: self.address,
                    TxnField.config_asset_clawback: self.address,
                    TxnField.config_asset_freeze: self.address,
                    TxnField.config_asset_reserve: self.address,
                    TxnField.fee: Int(0),
                }
            ),
            self.membership_token.set(InnerTxn.created_asset_id()),
            output.set(self.membership_token),
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def remove_member(self, member: abi.Address):
        return Pop(self.membership_records[member].delete())

    @external(authorize=Authorize.only(Global.creator_address()))
    def add_member(
        self, new_member: abi.Account, membership_token: abi.Asset = membership_token
    ):
        return Seq(
            (role := abi.Uint8()).set(Int(0)),
            (voted := abi.Bool()).set(consts.FALSE),
            (mr := MembershipRecord()).set(role, voted),
            self.membership_records[new_member.address()].set(mr),
            InnerTxnBuilder.Execute(
                clawback_axfer(
                    self.membership_token,
                    Int(1),
                    new_member.address(),
                    self.address,
                    extra={TxnField.fee: Int(0)},
                )
            ),
        )

    @external(read_only=True)
    def get_membership_record(self, member: abi.Address, *, output: MembershipRecord):
        return self.membership_records[member].store_into(output)

    @external(authorize=Authorize.holds_token(membership_token))
    def set_affirmation(
        self,
        idx: abi.Uint16,
        affirmation: Affirmation,
        membership_token: abi.Asset = membership_token,
    ):
        return self.affirmations[idx.get()].set(affirmation)

    @external(authorize=Authorize.holds_token(membership_token))
    def get_affirmation(
        self, membership_token: abi.Asset = membership_token, *, output: Affirmation
    ):
        return output.set(
            self.affirmations[Global.round() % self.affirmations.elements]
        )


class AppMember(Application):

    membership_token = ApplicationStateValue(TealType.uint64)
    club_app_id = ApplicationStateValue(TealType.uint64)
    last_affirmation = ApplicationStateValue(TealType.bytes)

    @external(authorize=Authorize.only(Global.creator_address()))
    def bootstrap(
        self,
        seed: abi.PaymentTransaction,
        app_id: abi.Application,
        membership_token: abi.Asset,
    ):
        return Seq(
            # Set app id
            self.club_app_id.set(app_id.application_id()),
            # Set membership token
            self.membership_token.set(membership_token.asset_id()),
            # Opt in to membership token
            InnerTxnBuilder.Execute(
                axfer(membership_token.asset_id(), Int(0), self.address)
                | {TxnField.fee: Int(0)},
            ),
        )

    @external
    def get_affirmation(
        self,
        member_token: abi.Asset = membership_token,
        club_app: abi.Application = club_app_id,
    ):
        return Seq(
            InnerTxnBuilder.ExecuteMethodCall(
                app_id=self.club_app_id,
                method_signature=get_method_signature(MembershipClub.get_affirmation),
                args=[member_token],
            ),
            self.last_affirmation.set(Suffix(InnerTxn.last_log(), Int(4))),
        )


if __name__ == "__main__":
    MembershipClub().dump("./artifacts")
