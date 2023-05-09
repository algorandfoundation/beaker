from ..localnet.kmd import (
    LocalAccount,
    get_localnet_default_wallet,
)

get_sandbox_default_wallet = get_localnet_default_wallet


class SandboxAccount(LocalAccount):
    pass
