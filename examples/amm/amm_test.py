import copy

import pytest
import typing

from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
    AccountTransactionSigner,
)
from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.encoding import decode_address
from beaker import client, sandbox, testing
from beaker.client.application_client import ApplicationClient
from beaker.client.logic_error import LogicException

from .amm import ConstantProductAMM

accts = sandbox.get_accounts()
algod_client: AlgodClient = sandbox.get_algod_client()

TOTAL_POOL_TOKENS = 10000000000
TOTAL_ASSET_TOKENS = 10000000000


@pytest.fixture(scope="session")
def creator_acct() -> tuple[str, str, AccountTransactionSigner]:
    return accts[0].address, accts[0].private_key, accts[0].signer


@pytest.fixture(scope="session")
def user_acct() -> tuple[str, str, AccountTransactionSigner]:
    return accts[1].address, accts[1].private_key, accts[1].signer


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

def minimum_fee_for_txn_count(sp: transaction.SuggestedParams, txn_count: int) -> transaction.SuggestedParams:
    s = copy.deepcopy(sp)
    s.flat_fee = True
    s.fee = transaction.constants.min_txn_fee * txn_count
    return s

def assert_app_algo_balance(c: client.ApplicationClient, expected_algos: int):
    """
    Verifies the app's algo balance is not unexpectedly drained during app interaction (e.g. paying inner transaction fees).
    """
    xs = testing.get_balances(c.client, [c.app_addr])
    assert c.app_addr in xs
    assert 0 in xs[c.app_addr]
    actual_algos = xs[c.app_addr][0]
    assert actual_algos == expected_algos

app_algo_balance: typing.Final = int(1e7)

def test_app_bootstrap(
    creator_app_client: client.ApplicationClient, assets: tuple[int, int]
):
    asset_a, asset_b = assets

    # Bootstrap to create pool token and set global state
    sp = creator_app_client.client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            creator_app_client.get_sender(), sp, creator_app_client.app_addr, app_algo_balance
        ),
        signer=creator_app_client.get_signer(),
    )
    result = creator_app_client.call(
        ConstantProductAMM.bootstrap, suggested_params=minimum_fee_for_txn_count(sp, 4), seed=ptxn, a_asset=asset_a, b_asset=asset_b
    )

    assert_app_algo_balance(creator_app_client, app_algo_balance)

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

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    _opt_in_to_token(addr, signer, pool_asset)

    balance_accts = [app_addr, addr]
    balances_before = testing.get_balances(creator_app_client.client, balance_accts)

    a_amount = 10000
    b_amount = 3000

    sp = creator_app_client.client.suggested_params()
    creator_app_client.call(
        ConstantProductAMM.mint,
        suggested_params=minimum_fee_for_txn_count(sp, 2),
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, a_amount, a_asset),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, b_amount, b_asset),
            signer=signer,
        ),
        pool_asset=pool_asset,
        a_asset=a_asset,
        b_asset=b_asset,
    )

    balances_after = testing.get_balances(creator_app_client.client, balance_accts)
    balance_deltas = testing.get_deltas(balances_before, balances_after)

    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    assert_app_algo_balance(creator_app_client, app_algo_balance)

    expected_pool_tokens = int((a_amount * b_amount) ** 0.5 - ConstantProductAMM._scale)
    assert balance_deltas[addr][pool_asset] == expected_pool_tokens

    ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = int((a_amount * ConstantProductAMM._scale) / b_amount)
    assert ratio == expected_ratio


def test_mint(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    balances_before = testing.get_balances(creator_app_client.client, [app_addr, addr])

    ratio_before = _get_ratio_from_state(creator_app_client)

    a_amount = 40000
    b_amount = int(a_amount * ConstantProductAMM._scale / ratio_before)

    sp = creator_app_client.client.suggested_params()
    creator_app_client.call(
        ConstantProductAMM.mint,
        suggested_params=minimum_fee_for_txn_count(sp, 2),
        a_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, a_amount, a_asset),
            signer=signer,
        ),
        b_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, b_amount, b_asset),
            signer=signer,
        ),
        pool_asset=pool_asset,
        a_asset=a_asset,
        b_asset=b_asset,
    )

    balances_after = testing.get_balances(creator_app_client.client, [app_addr, addr])
    balance_deltas = testing.get_deltas(balances_before, balances_after)

    # App got the right amount
    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    ##
    assert_app_algo_balance(creator_app_client, app_algo_balance)

    # We minted the correct amount of pool tokens
    issued = TOTAL_POOL_TOKENS - balances_before[app_addr][pool_asset]
    expected_pool_tokens = _get_tokens_to_mint(
        issued,
        a_amount,
        balances_before[app_addr][a_asset],
        b_amount,
        balances_before[app_addr][b_asset],
        ConstantProductAMM._scale,
    )
    assert balance_deltas[addr][pool_asset] == int(expected_pool_tokens)

    # We updated the ratio accordingly
    actual_ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert actual_ratio == expected_ratio


def test_bad_mint(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    a_amount = 40000
    b_amount = 1000

    sp = creator_app_client.client.suggested_params()

    try:
        creator_app_client.call(
            ConstantProductAMM.mint,
            a_xfer=TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 0, a_asset),
                signer=signer,
            ),
            b_xfer=TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, b_amount, b_asset),
                signer=signer,
            ),
            pool_asset=pool_asset,
            a_asset=a_asset,
            b_asset=b_asset,
        )
    except LogicException as le:
        assert le.msg.startswith("assert failed")

    try:
        creator_app_client.call(
            ConstantProductAMM.mint,
            a_xfer=TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, a_amount, a_asset),
                signer=signer,
            ),
            b_xfer=TransactionWithSigner(
                txn=transaction.AssetTransferTxn(addr, sp, app_addr, 0, b_asset),
                signer=signer,
            ),
            pool_asset=pool_asset,
            a_asset=a_asset,
            b_asset=b_asset,
        )
    except LogicException as le:
        assert le.msg.startswith("assert failed")


def test_burn(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    balances_before = testing.get_balances(creator_app_client.client, [app_addr, addr])

    burn_amt = balances_before[addr][pool_asset] // 10

    sp = creator_app_client.client.suggested_params()

    creator_app_client.call(
        ConstantProductAMM.burn,
        suggested_params=minimum_fee_for_txn_count(sp, 3),
        pool_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, burn_amt, pool_asset),
            signer=signer,
        ),
        pool_asset=pool_asset,
        a_asset=a_asset,
        b_asset=b_asset,
    )

    balances_after = testing.get_balances(creator_app_client.client, [app_addr, addr])
    balances_delta = testing.get_deltas(balances_before, balances_after)

    assert balances_delta[app_addr][pool_asset] == burn_amt

    # We minted the correct amount of pool tokens
    issued = TOTAL_POOL_TOKENS - balances_before[app_addr][pool_asset]
    a_supply = balances_before[app_addr][a_asset]
    b_supply = balances_before[app_addr][b_asset]

    expected_a_tokens = _get_tokens_to_burn(a_supply, burn_amt, issued)
    assert balances_delta[addr][a_asset] == int(expected_a_tokens)

    expected_b_tokens = _get_tokens_to_burn(b_supply, burn_amt, issued)
    assert balances_delta[addr][b_asset] == int(expected_b_tokens)

    assert_app_algo_balance(creator_app_client, app_algo_balance)

    ratio_after = _get_ratio_from_state(creator_app_client)

    # Ratio should be identical?
    # assert ratio_before == ratio_after

    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert ratio_after == expected_ratio


def test_swap(creator_app_client: ApplicationClient):
    app_addr, addr, signer = (
        creator_app_client.app_addr,
        creator_app_client.sender,
        creator_app_client.signer,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    balances_before = testing.get_balances(creator_app_client.client, [app_addr, addr])

    swap_amt = balances_before[addr][a_asset] // 10

    sp = creator_app_client.client.suggested_params()
    creator_app_client.call(
        ConstantProductAMM.swap,
        suggested_params=minimum_fee_for_txn_count(sp, 2),
        swap_xfer=TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, swap_amt, a_asset),
            signer=signer,
        ),
        pool_asset=pool_asset,
        a_asset=a_asset,
        b_asset=b_asset,
    )

    balances_after = testing.get_balances(creator_app_client.client, [app_addr, addr])
    balances_delta = testing.get_deltas(balances_before, balances_after)

    assert balances_delta[app_addr][a_asset] == swap_amt

    # We minted the correct amount of pool tokens
    a_supply = balances_before[app_addr][a_asset]
    b_supply = balances_before[app_addr][b_asset]

    expected_b_tokens = _get_tokens_to_swap(
        swap_amt, a_supply, b_supply, ConstantProductAMM._scale, ConstantProductAMM._fee
    )
    assert balances_delta[addr][b_asset] == int(expected_b_tokens)

    assert_app_algo_balance(creator_app_client, app_algo_balance)

    ratio_after = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
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
