import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property

from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk.kmd import KMDClient
from algosdk.wallet import Wallet

DEFAULT_KMD_ADDRESS = "http://localhost:4002"
DEFAULT_KMD_TOKEN = "a" * 64
DEFAULT_KMD_WALLET_NAME = "unencrypted-default-wallet"
DEFAULT_KMD_WALLET_PASSWORD = ""


def get_client() -> KMDClient:
    """creates a new kmd client using the default sandbox parameters"""
    return KMDClient(kmd_token=DEFAULT_KMD_TOKEN, kmd_address=DEFAULT_KMD_ADDRESS)


def get_sandbox_default_wallet() -> Wallet:
    """returns the default sandbox kmd wallet"""
    return Wallet(
        wallet_name=DEFAULT_KMD_WALLET_NAME,
        wallet_pswd=DEFAULT_KMD_WALLET_PASSWORD,
        kmd_client=get_client(),
    )


@dataclass(kw_only=True)
class SandboxAccount:
    """SandboxAccount is a simple dataclass to hold a sandbox account details"""

    #: The address of a sandbox account
    address: str
    #: The base64 encoded private key of the account
    private_key: str

    #: An AccountTransactionSigner that can be used as a TransactionSigner
    @cached_property
    def signer(self) -> AccountTransactionSigner:
        return AccountTransactionSigner(self.private_key)


def get_accounts(
    kmd_address: str = DEFAULT_KMD_ADDRESS,
    kmd_token: str = DEFAULT_KMD_TOKEN,
    wallet_name: str = DEFAULT_KMD_WALLET_NAME,
    wallet_password: str = DEFAULT_KMD_WALLET_PASSWORD,
) -> list[SandboxAccount]:
    """gets all the accounts in the sandbox kmd, defaults
    to the `unencrypted-default-wallet` created on private networks automatically"""
    kmd = KMDClient(kmd_token, kmd_address)
    with wallet_handle_by_name(kmd, wallet_name, wallet_password) as wallet_handle:
        return [
            SandboxAccount(
                address=address,
                private_key=kmd.export_key(wallet_handle, wallet_password, address),
            )
            for address in kmd.list_keys(wallet_handle)
        ]


def add_account(
    private_key: str,
    kmd_address: str = DEFAULT_KMD_ADDRESS,
    kmd_token: str = DEFAULT_KMD_TOKEN,
    wallet_name: str = DEFAULT_KMD_WALLET_NAME,
    wallet_password: str = DEFAULT_KMD_WALLET_PASSWORD,
) -> str:
    """Adds a new account to the sandbox kmd"""
    kmd = KMDClient(kmd_token, kmd_address)
    with wallet_handle_by_name(kmd, wallet_name, wallet_password) as wallet_handle:
        return kmd.import_key(wallet_handle, private_key)


def delete_account(
    address: str,
    kmd_address: str = DEFAULT_KMD_ADDRESS,
    kmd_token: str = DEFAULT_KMD_TOKEN,
    wallet_name: str = DEFAULT_KMD_WALLET_NAME,
    wallet_password: str = DEFAULT_KMD_WALLET_PASSWORD,
) -> None:
    """Deletes an existing account from the sandbox kmd"""
    kmd = KMDClient(kmd_token, kmd_address)
    with wallet_handle_by_name(kmd, wallet_name, wallet_password) as wallet_handle:
        kmd.delete_key(wallet_handle, wallet_password, address)


@contextlib.contextmanager
def wallet_handle_by_name(
    kmd: KMDClient, wallet_name: str, wallet_password: str
) -> Iterator[str]:

    wallets = kmd.list_wallets()

    try:
        wallet_id = next(iter(w["id"] for w in wallets if w["name"] == wallet_name))
    except StopIteration:
        raise Exception(f"Wallet not found: {wallet_name}") from None

    wallet_handle = kmd.init_wallet_handle(wallet_id, wallet_password)
    try:
        yield wallet_handle
    finally:
        kmd.release_wallet_handle(wallet_handle)
