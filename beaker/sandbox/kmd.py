from ..localnet.kmd import (
    DEFAULT_KMD_ADDRESS,
    DEFAULT_KMD_TOKEN,
    DEFAULT_KMD_WALLET_NAME,
    DEFAULT_KMD_WALLET_PASSWORD,
    LocalAccount,
    add_account,
    delete_account,
    get_accounts,
    get_client,
    get_localnet_default_wallet,
    wallet_handle_by_name,
)

get_sandbox_default_wallet = get_localnet_default_wallet


class SandboxAccount(LocalAccount):
    pass


__all__ = [
    "get_client",
    "get_sandbox_default_wallet",
    "SandboxAccount",
    "get_accounts",
    "add_account",
    "delete_account",
    "wallet_handle_by_name",
    "DEFAULT_KMD_ADDRESS",
    "DEFAULT_KMD_TOKEN",
    "DEFAULT_KMD_WALLET_NAME",
    "DEFAULT_KMD_WALLET_PASSWORD",
]
