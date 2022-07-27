from ast import Constant
import pytest

from algosdk.atomic_transaction_composer import *
from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.encoding import decode_address
from beaker import client, sandbox
from beaker.client.application_client import ApplicationClient

from .amm import ConstantProductAMM

accts = sandbox.get_accounts()
algod_client: AlgodClient = sandbox.get_client()

TOTAL_POOL_TOKENS = 10000000000
TOTAL_ASSET_TOKENS = 10000000000
POOL_IDX = 0
A_IDX = 1
B_IDX = 2


@pytest.fixture(scope="session")
def creator_acct() -> tuple[str, str, AccountTransactionSigner]:
    addr, sk = accts[0]
    return (addr, sk, AccountTransactionSigner(sk))


@pytest.fixture(scope="session")
def user_acct() -> tuple[str, str, AccountTransactionSigner]:
    addr, sk = accts[1]
    return (addr, sk, AccountTransactionSigner(sk))


@pytest.fixture(scope="session")
def assets(creator_acct) -> tuple[int, int]:
    addr, sk, signer = creator_acct
    sp = algod_client.suggested_params()
    txns: list[transaction.Transaction] = transaction.assign_group_id(
        [
            transaction.AssetCreateTxn(
                addr,
                sp,
                TOTAL_ASSET_TOKENS,
                0,
                False,
                asset_name="asset a",
                unit_name="A",
            ),
            transaction.AssetCreateTxn(
                addr,
                sp,
                TOTAL_ASSET_TOKENS,
                0,
                False,
                asset_name="asset b",
                unit_name="B",
            ),
        ]
    )
    algod_client.send_transactions([txn.sign(sk) for txn in txns])
    results = [
        transaction.wait_for_confirmation(algod_client, txid, 4)
        for txid in [t.get_txid() for t in txns]
    ]
    return (results[0]["asset-index"], results[1]["asset-index"])


@pytest.fixture(scope="session")
def creator_app_client(creator_acct) -> client.ApplicationClient:
    _, _, signer = creator_acct
    app = ConstantProductAMM()
    app_client = client.ApplicationClient(algod_client, app, signer=signer)
    return app_client


def test_app_create(creator_app_client: client.ApplicationClient):
    creator_app_client.create()
    app_state = creator_app_client.get_application_state()
    sender = creator_app_client.get_sender()

    assert (
        app_state[ConstantProductAMM.governor.str_key()] == decode_address(sender).hex()
    ), "The governor should be my address"
    assert app_state[ConstantProductAMM.ratio.str_key()] == 0, "The ratio should be 0"


def test_app_bootstrap(
    creator_app_client: client.ApplicationClient, assets: tuple[int, int]
):
    asset_a, asset_b = assets

    # Bootstrap to create pool token and set global state
    sp = creator_app_client.client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            creator_app_client.get_sender(), sp, creator_app_client.app_addr, int(1e7)
        ),
        signer=creator_app_client.get_signer(),
    )
    result = creator_app_client.call(
        ConstantProductAMM.bootstrap, seed=ptxn, a_asset=asset_a, b_asset=asset_b
    )
    pool_token = result.return_value
    assert pool_token > 0, "We should have created a pool token with asset id>0"

    # Check pool token params
    token_info = creator_app_client.client.asset_info(pool_token)
    assert token_info["params"]["name"] == "DPT-A-B"
    assert token_info["params"]["total"] == TOTAL_POOL_TOKENS
    assert token_info["params"]["reserve"] == creator_app_client.app_addr
    assert token_info["params"]["manager"] == creator_app_client.app_addr
    assert token_info["params"]["creator"] == creator_app_client.app_addr

    # Make sure we're opted in
    ai = creator_app_client.get_application_account_info()
    assert len(ai["assets"]) == 3, "Should have 3 assets, A/B/Pool"

    # Make sure our state is updated
    app_state = creator_app_client.get_application_state()
    assert app_state[ConstantProductAMM.pool_token.str_key()] == pool_token
    assert app_state[ConstantProductAMM.asset_a.str_key()] == asset_a
    assert app_state[ConstantProductAMM.asset_b.str_key()] == asset_b


def test_app_fund(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    asset_list = _get_tokens_from_state(creator_app_client)
    _opt_in_to_token(addr, signer, asset_list[POOL_IDX])

    app_before, creator_before = _get_balances([app_addr, addr], asset_list)

    a_amount = 10000
    b_amount = 3000

    sp = algod_client.suggested_params()
    creator_app_client.call(
        ConstantProductAMM.mint,
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(
                addr, sp, app_addr, a_amount, asset_list[A_IDX]
            ),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(
                addr, sp, app_addr, b_amount, asset_list[B_IDX]
            ),
            signer=signer,
        ),
        pool_asset=asset_list[POOL_IDX],
        a_asset=asset_list[A_IDX],
        b_asset=asset_list[B_IDX],
    )

    app_after, creator_after = _get_balances([app_addr, addr], asset_list)

    creator_deltas = [creator_before[idx] - creator_after[idx] for idx in range(3)]
    app_deltas = [app_before[idx] - app_after[idx] for idx in range(3)]

    # We didn't lose any tokens
    assert creator_deltas[0] == -1 * app_deltas[0]
    assert creator_deltas[1] == -1 * app_deltas[1]
    assert creator_deltas[2] == -1 * app_deltas[2]

    assert creator_deltas[A_IDX] == a_amount
    assert creator_deltas[B_IDX] == b_amount

    expected_pool_tokens = int((a_amount * b_amount) ** 0.5 - ConstantProductAMM._scale)
    assert app_deltas[POOL_IDX] == expected_pool_tokens

    ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = int((a_amount * ConstantProductAMM._scale) / b_amount)
    assert ratio == expected_ratio


def test_mint(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    asset_list = _get_tokens_from_state(creator_app_client)

    app_before, creator_before = _get_balances([app_addr, addr], asset_list)

    ratio_before = _get_ratio_from_state(creator_app_client)

    a_amount = 40000
    b_amount = int(a_amount * ConstantProductAMM._scale / ratio_before)

    sp = algod_client.suggested_params()
    creator_app_client.call(
        ConstantProductAMM.mint,
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(
                addr, sp, app_addr, a_amount, asset_list[A_IDX]
            ),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(
                addr, sp, app_addr, b_amount, asset_list[B_IDX]
            ),
            signer=signer,
        ),
        pool_asset=asset_list[POOL_IDX],
        a_asset=asset_list[A_IDX],
        b_asset=asset_list[B_IDX],
    )

    app_after, creator_after = _get_balances([app_addr, addr], asset_list)

    creator_deltas = [
        creator_before[idx] - creator_after[idx] for idx in range(len(asset_list))
    ]
    app_deltas = [app_before[idx] - app_after[idx] for idx in range(len(asset_list))]

    assert (
        sum([creator_deltas[idx] + app_deltas[idx] for idx in range(len(asset_list))])
        == 0
    ), "We lost tokens somewhere?"

    # Creator lost the right amount
    assert creator_deltas[A_IDX] == a_amount
    assert creator_deltas[B_IDX] == b_amount

    # We minted the correct amount of pool tokens
    issued = TOTAL_POOL_TOKENS - app_before[POOL_IDX]
    expected_pool_tokens = _get_tokens_to_mint(
        issued,
        a_amount,
        app_before[A_IDX],
        b_amount,
        app_before[B_IDX],
        ConstantProductAMM._scale,
    )
    assert app_deltas[POOL_IDX] == int(expected_pool_tokens)

    # We updated the ratio accordingly
    actual_ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(app_after[A_IDX], app_after[B_IDX])
    assert actual_ratio == expected_ratio


def test_burn(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    asset_list = _get_tokens_from_state(creator_app_client)

    ratio_before = _get_ratio_from_state(creator_app_client)

    app_before, creator_before = _get_balances([app_addr, addr], asset_list)

    burn_amt = creator_before[POOL_IDX] // 10

    sp = algod_client.suggested_params()

    try:
        creator_app_client.call(
            ConstantProductAMM.burn,
            pool_xfer=TransactionWithSigner(
                txn=transaction.AssetTransferTxn(
                    addr, sp, app_addr, burn_amt, asset_list[POOL_IDX]
                ),
                signer=signer,
            ),
            pool_asset=asset_list[POOL_IDX],
            a_asset=asset_list[A_IDX],
            b_asset=asset_list[B_IDX],
        )
    except Exception as e:
        print(creator_app_client.wrap_approval_exception(e))

    app_after, creator_after = _get_balances([app_addr, addr], asset_list)

    creator_deltas = [
        creator_before[idx] - creator_after[idx] for idx in range(len(asset_list))
    ]
    app_deltas = [app_before[idx] - app_after[idx] for idx in range(len(asset_list))]

    assert (
        sum([creator_deltas[idx] + app_deltas[idx] for idx in range(len(asset_list))])
        == 0
    ), "We lost tokens somewhere?"

    assert creator_deltas[POOL_IDX] == burn_amt

    # We minted the correct amount of pool tokens
    issued = TOTAL_POOL_TOKENS - app_before[POOL_IDX]
    a_supply = app_before[A_IDX]
    b_supply = app_before[B_IDX]

    expected_a_tokens = _get_tokens_to_burn(a_supply, burn_amt, issued)
    assert app_deltas[A_IDX] == int(expected_a_tokens)

    expected_b_tokens = _get_tokens_to_burn(b_supply, burn_amt, issued)
    assert app_deltas[B_IDX] == int(expected_b_tokens)

    ratio_after = _get_ratio_from_state(creator_app_client)

    # Ratio should be identical?
    # assert ratio_before == ratio_after

    expected_ratio = _expect_ratio(app_after[A_IDX], app_after[B_IDX])
    assert ratio_after == expected_ratio


def test_swap(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    asset_list = _get_tokens_from_state(creator_app_client)

    app_before, creator_before = _get_balances([app_addr, addr], asset_list)

    swap_amt = creator_before[A_IDX] // 10

    sp = algod_client.suggested_params()

    creator_app_client.call(
        ConstantProductAMM.swap,
        swap_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(
                addr, sp, app_addr, swap_amt, asset_list[A_IDX]
            ),
            signer=signer,
        ),
        pool_asset=asset_list[POOL_IDX],
        a_asset=asset_list[A_IDX],
        b_asset=asset_list[B_IDX],
    )

    app_after, creator_after = _get_balances([app_addr, addr], asset_list)

    creator_deltas = [creator_before[idx] - creator_after[idx] for idx in range(3)]
    app_deltas = [app_before[idx] - app_after[idx] for idx in range(3)]

    # We didn't lose any tokens
    assert (
        sum([creator_deltas[idx] + app_deltas[idx] for idx in range(len(asset_list))])
        == 0
    ), "We lost tokens somewhere?"

    assert creator_deltas[A_IDX] == swap_amt

    # We minted the correct amount of pool tokens
    a_supply = app_before[A_IDX]
    b_supply = app_before[B_IDX]

    expected_b_tokens = _get_tokens_to_swap(
        swap_amt, a_supply, b_supply, ConstantProductAMM._scale, ConstantProductAMM._fee
    )
    assert app_deltas[B_IDX] == int(expected_b_tokens)

    ratio_after = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(app_after[A_IDX], app_after[B_IDX])
    assert ratio_after == expected_ratio


def _get_tokens_to_mint(
    issued: int, a_amt: int, a_supply: int, b_amt: int, b_supply: int, scale: int
) -> int:
    a_ratio = (a_amt * scale) / a_supply
    b_ratio = (b_amt * scale) / b_supply

    if a_ratio < b_ratio:
        return int((a_ratio * issued) / scale)

    return int((b_ratio * issued) / scale)


def _get_tokens_to_swap(in_amount, in_supply, out_supply, scale, fee) -> int:
    factor = scale - fee
    return int(
        (in_amount * factor * out_supply) / ((in_supply * scale) + (in_amount * factor))
    )


def _get_tokens_to_burn(asset_supply, burn_amount, pool_issued):
    return int((asset_supply * burn_amount) / pool_issued)


def _get_ratio_from_state(creator_app_client: ApplicationClient):
    app_state = creator_app_client.get_application_state()
    return app_state[ConstantProductAMM.ratio.str_key()]


def _get_tokens_from_state(
    creator_app_client: ApplicationClient,
) -> tuple[int, int, int]:
    app_state = creator_app_client.get_application_state()
    return (
        app_state[ConstantProductAMM.pool_token.str_key()],
        app_state[ConstantProductAMM.asset_a.str_key()],
        app_state[ConstantProductAMM.asset_b.str_key()],
    )


def _get_balances(addrs: list[str], assets: list[int]) -> list[list[int]]:
    balances: list[list[int]] = []

    for addr in addrs:
        addr_bals = {
            asset["asset-id"]: asset["amount"]
            for asset in algod_client.account_info(addr)["assets"]
            if asset["asset-id"] in assets
        }
        balances.append([addr_bals[asset] for asset in assets])

    return balances


def _expect_ratio(a_sup, b_sup):
    return int((a_sup * ConstantProductAMM._scale) / b_sup)


def _opt_in_to_token(addr: str, signer: AccountTransactionSigner, id: int):
    sp = algod_client.suggested_params()
    atc = AtomicTransactionComposer()
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, addr, 0, id),
            signer=signer,
        )
    )
    atc.execute(algod_client, 2)
