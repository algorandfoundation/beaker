import algosdk
import base64
from pyteal import *
from beaker import *
from application import MembershipRecord, Boxen


def print_boxes(app_client: client.ApplicationClient):
    record_codec = algosdk.abi.ABIType.from_string(str(MembershipRecord().type_spec()))
    boxes = app_client.client.application_boxes(app_client.app_id)
    print(f"{len(boxes['boxes'])} boxes found")
    for box in boxes["boxes"]:
        name = base64.b64decode(box["name"])
        contents = app_client.client.application_box_by_name(app_client.app_id, name)
        membership_record = record_codec.decode(base64.b64decode(contents["value"]))
        print(f"\t{algosdk.encoding.encode_address(name)} => {membership_record} ")


def demo():
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


if __name__ == "__main__":
    demo()
