import base64
import algosdk
from pyteal import *
from beaker import *


# Box Consensus params

# BoxFlatMinBalance = 0.002500
# BoxByteMinBalance = 0.000400

# MaxBoxSize = 4 * 8096
# MaxAppBoxReferences = 8
# BytesPerBoxReference = 1024

# Max box bytes accessible in 1 app call: 8k
# Max box bytes accessible in 16 app calls: 128k

# name = Bytes("name")
# val = Bytes("val")
# size = Int(1)
# start = Int(1)
#
# BoxCreate(name, size) # Create a new box of size
# BoxDelete(name) # Delete box
#
# BoxExtract(name, start, size) # Get `size` bytes from box starting from `start`
# BoxReplace(name, start, val) # Overwrite whatever is in the box from start to len(val)
# BoxPut(name, val) # Write all contents of `val` to box starting from 0
#
# BoxGet(name) # Get the full contents of this box (will panic >4k)
# BoxLen(name) # Get the size of this box
#

# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


class MapElement:
    def __init__(self, key: Expr, value_type: type[abi.BaseType]):
        assert key.type_of() == TealType.bytes, TealTypeError(
            key.type_of(), TealType.bytes
        )

        self.key = key
        self.value_type = value_type

    def store_into(self, val: abi.BaseType)->Expr:
        # Assert same type, compile time check
        return val.decode(self.get())

    def get(self) -> Expr:
        return Seq(maybe := BoxGet(self.key), Assert(maybe.hasValue()), maybe.value())

    def set(self, val: abi.BaseType | Expr) -> Expr:
        # TODO: does BoxPut work if it needs to be resized later?
        match val:
            case abi.BaseType():
                return BoxPut(self.key, val.encode())
            case Expr():
                if val.type_of() != TealType.bytes:
                    raise TealTypeError(val.type_of(), TealType.bytes)
                return BoxPut(self.key, val)

    def delete(self) -> Expr:
        return BoxDelete(self.key)


class Mapping:
    def __init__(self, key_type: type[abi.BaseType], value_type: type[abi.BaseType]):
        self.key_type = key_type
        self.value_type = value_type

    def __getitem__(self, idx: abi.BaseType | Expr):
        match idx:
            case abi.BaseType():
                return MapElement(idx.encode(), self.value_type)
            case Expr():
                if idx.type_of() != TealType.bytes:
                    raise TealTypeError(idx.type_of(), TealType.bytes)
                return MapElement(idx, self.value_type)


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


def print_boxes(app_client: client.ApplicationClient):
    record_codec = algosdk.abi.ABIType.from_string(str(MembershipRecord().type_spec()))
    boxes = app_client.client.application_boxes(app_client.app_id)
    print(f"{len(boxes['boxes'])} boxes found")
    for box in boxes["boxes"]:
        name = base64.b64decode(box["name"])
        contents = app_client.client.application_box_by_name(app_client.app_id, name)
        membership_record = record_codec.decode(base64.b64decode(contents["value"]))
        print(f"\t{algosdk.encoding.encode_address(name)} => {membership_record} ")


if __name__ == "__main__":
    accts = sandbox.get_accounts()
    acct = accts.pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), Boxen(), signer=acct.signer
    )
    app_client.create()
    app_client.fund(100 * consts.algo)

    app_client.call(
        Boxen.add_member,
        boxes=[[app_client.app_id, algosdk.encoding.decode_address(acct.address)]],
    )
    print_boxes(app_client)

    result = app_client.call(Boxen.get_membership_record, member=acct.address, boxes=[[app_client.app_id, algosdk.encoding.decode_address(acct.address)]])
    print(result.return_value)

    app_client.call(
        Boxen.remove_member,
        boxes=[[app_client.app_id, algosdk.encoding.decode_address(acct.address)]],
        member=acct.address,
    )
    print_boxes(app_client)

