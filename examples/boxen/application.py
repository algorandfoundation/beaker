from pyteal import *
from beaker import *

from beaker.lib.txn import clawback_axfer
from beaker.lib.storage import Mapping

# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


BoxFlatMinBalance = 2500
BoxByteMinBalance = 400
AssetMinBalance = 100000


class MembershipClub(Application):

    membership_records = Mapping(abi.Address, MembershipRecord)
    membership_token = ApplicationStateValue(
        TealType.uint64, static=True, descr="The asset that represents membership of this club"
    )

    _max_members = 1000
    MaxMembers = Int(_max_members)

    _box_size = abi.size_of(MembershipRecord)

    _min_balance = (
        AssetMinBalance # Cover min bal for member token
        + (BoxFlatMinBalance + (_box_size * BoxByteMinBalance)) * _max_members # cover min bal for boxes we might create
    )
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
                    self.membership_token, Int(1), new_member.address(), self.address
                )
                | {TxnField.fee: Int(0)}
            ),
        )

    @external(read_only=True)
    def get_membership_record(self, member: abi.Address, *, output: MembershipRecord):
        return self.membership_records[member].store_into(output)


if __name__ == "__main__":
    MembershipClub().dump("./artifacts")
