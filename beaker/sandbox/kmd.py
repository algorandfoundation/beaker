from typing import Tuple
from algosdk.kmd import KMDClient

DEFAULT_KMD_ADDRESS = "http://localhost:4002"
DEFAULT_KMD_TOKEN = "a" * 64
DEFAULT_KMD_WALLET_NAME = "unencrypted-default-wallet"
DEFAULT_KMD_WALLET_PASSWORD = ""


def get_accounts(
    kmd_address: str = DEFAULT_KMD_ADDRESS,
    kmd_token: str = DEFAULT_KMD_TOKEN,
    wallet_name: str = DEFAULT_KMD_WALLET_NAME,
    wallet_password: str = DEFAULT_KMD_WALLET_PASSWORD,
) -> list[Tuple[str, str]]:

    kmd = KMDClient(kmd_token, kmd_address)
    wallets = kmd.list_wallets()

    walletID = None
    for wallet in wallets:
        if wallet["name"] == wallet_name:
            walletID = wallet["id"]
            break

    if walletID is None:
        raise Exception("Wallet not found: {}".format(wallet_name))

    walletHandle = kmd.init_wallet_handle(walletID, wallet_password)

    try:
        addresses = kmd.list_keys(walletHandle)
        privateKeys = [
            kmd.export_key(walletHandle, wallet_password, addr) for addr in addresses
        ]
        kmdAccounts = [(addresses[i], privateKeys[i]) for i in range(len(privateKeys))]
    finally:
        kmd.release_wallet_handle(walletHandle)

    return kmdAccounts
