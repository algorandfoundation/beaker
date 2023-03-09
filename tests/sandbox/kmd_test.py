import pytest
from algosdk.account import generate_account
from algosdk.error import KMDHTTPError

from beaker.sandbox.kmd import (
    DEFAULT_KMD_ADDRESS,
    DEFAULT_KMD_TOKEN,
    DEFAULT_KMD_WALLET_NAME,
    DEFAULT_KMD_WALLET_PASSWORD,
    add_account,
    delete_account,
    get_accounts,
    get_client,
    get_sandbox_default_wallet,
)

pytestmark = pytest.mark.network


def test_get_accounts() -> None:
    accts = get_accounts()
    assert (
        len(accts) > 0
    ), "Should have accounts (make sure its a sandbox with default wallet settings)"


def test_add_remove_account() -> None:
    pk, addr = generate_account()
    addr_added = add_account(pk)
    assert addr == addr_added, "Expected added address to match generated address"

    with pytest.raises(KMDHTTPError):
        add_account("lol")

    delete_account(addr_added)

    with pytest.raises(KMDHTTPError):
        delete_account("lol")


def test_get_client() -> None:
    kmd_client = get_client()
    assert kmd_client.kmd_address == DEFAULT_KMD_ADDRESS
    assert kmd_client.kmd_token == DEFAULT_KMD_TOKEN
    kmd_client.list_wallets()


def test_get_sandbox_default_wallet() -> None:
    sandbox_default_wallet = get_sandbox_default_wallet()
    assert sandbox_default_wallet.name == DEFAULT_KMD_WALLET_NAME
    assert sandbox_default_wallet.pswd == DEFAULT_KMD_WALLET_PASSWORD
    sandbox_default_wallet.list_keys()
