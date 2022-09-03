import base64
from typing import Literal
import algosdk
from pyteal import *
from beaker import *


class MapElement:
    def __init__(self, key: Expr, value_type: type[abi.BaseType]):
        assert key.type_of() == TealType.bytes, TealTypeError(
            key.type_of(), TealType.bytes
        )

        self.key = key
        self.value_type = value_type

    def store_into(self, val: abi.BaseType) -> Expr:
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

    def __getitem__(self, idx: abi.BaseType | Expr) -> MapElement:
        match idx:
            case abi.BaseType():
                return MapElement(idx.encode(), self.value_type)
            case Expr():
                if idx.type_of() != TealType.bytes:
                    raise TealTypeError(idx.type_of(), TealType.bytes)
                return MapElement(idx, self.value_type)


class ListElement:
    def __init__(self, name, size, idx):
        self.name = name
        self.size = size
        self.idx = idx

    def store_into(self, val: abi.BaseType) -> Expr:
        return val.decode(self.get())

    def get(self) -> Expr:
        return BoxExtract(self.name, self.size * self.idx, self.size)

    def set(self, val: abi.BaseType) -> Expr:
        return BoxReplace(self.name, self.size * self.idx, val.encode())


class Listing:
    def __init__(self, name: Bytes, value_type: type[abi.BaseType], elements: int):
        ts = abi.type_spec_from_annotation(value_type)
        assert not ts.is_dynamic()

        assert ts.byte_length_static() * elements < 32e3

        self.name = name

        self.value_type = ts

        self._element_size = ts.byte_length_static()
        self.element_size = Int(self._element_size)

        self._elements = elements
        self.elements = Int(self._elements)

    def create(self) -> Expr:
        return BoxCreate(self.name, self.element_size * self.elements)

    def __getitem__(self, idx: Int) -> ListElement:
        return ListElement(self.name, self.element_size, idx)


# Use a box per member to denote membership parameters
class MembershipRecord(abi.NamedTuple):
    role: abi.Field[abi.Uint8]
    voted: abi.Field[abi.Bool]


class Votable(abi.NamedTuple):
    title: abi.Field[abi.StaticBytes[Literal[32]]]
    yes_votes: abi.Field[abi.Uint8]
    no_votes: abi.Field[abi.Uint8]


class Boxen(Application):

    membership = Mapping(abi.Address, MembershipRecord)
    votables = Listing(Bytes("votables"), Votable, 3)

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

    @external
    def add_votable(self, votable: Votable):
        return self.votables[Int(0)].set(votable)


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

    result = app_client.call(
        Boxen.get_membership_record,
        member=acct.address,
        boxes=[[app_client.app_id, algosdk.encoding.decode_address(acct.address)]],
    )
    print(result.return_value)

    app_client.call(
        Boxen.remove_member,
        boxes=[[app_client.app_id, algosdk.encoding.decode_address(acct.address)]],
        member=acct.address,
    )
    print_boxes(app_client)
