# import pytest

# from algosdk.account import generate_account
# from algosdk.error import KMDHTTPError
from .kmd import get_accounts  # , add_account


def test_get_accounts():
    accts = get_accounts()
    assert (
        len(accts) > 0
    ), "Should have accounts (make sure its a sandbox with default wallet settings)"


# TODO: add back when we have delete
# def test_add_remove_account():
#    pk, addr = generate_account()
#    addr_added = add_account(pk)
#    assert addr == addr_added, "Expected added address to match generated address"
#
#    with pytest.raises(KMDHTTPError):
#        add_account("lol")
#
