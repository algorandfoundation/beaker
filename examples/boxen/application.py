from typing import Literal
from pyteal import *
from beaker import *

from beaker.lib.storage import Mapping

# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


class Boxen(Application):
    membership = Mapping(abi.Address, MembershipRecord)

    @external
    def add_member(self):
        return Seq(
            (role := abi.Uint8()).set(Int(0)),
            (voted := abi.Bool()).set(consts.FALSE),
            (mr := MembershipRecord()).set(role, voted),
            self.membership[Txn.sender()].set(mr),
        )

    @external
    def get_membership_record(self, member: abi.Address, *, output: MembershipRecord):
        return self.membership[member].store_into(output)

    @external
    def remove_member(self, member: abi.Address):
        return Pop(self.membership[member].delete())


if __name__ == "__main__":
    Boxen().dump("./artifacts")
