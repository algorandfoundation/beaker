import copy
import itertools
import typing
from dataclasses import dataclass

import pyteal as pt
import pytest
from algokit_utils import LogicError
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
    abi,
)
from algosdk.encoding import decode_address
from algosdk.source_map import SourceMap

from beaker import client, consts, sandbox

from tests import helpers
from tests.conftest import check_application_artifacts_output_stability

from examples.amm import amm, demo

accts = sandbox.get_accounts()
algod_client = sandbox.get_algod_client()

TOTAL_POOL_TOKENS = 10000000000
TOTAL_ASSET_TOKENS = 10000000000


AcctInfo = tuple[str, str, AccountTransactionSigner]
AssertTestCase = tuple[
    str,
    abi.Method | pt.ABIReturnSubroutine | str,
    dict[str, typing.Any],
    client.ApplicationClient,
]


@pytest.fixture(scope="session")
def creator_acct() -> AcctInfo:
    return accts[0].address, accts[0].private_key, accts[0].signer


@pytest.fixture(scope="session")
def user_acct() -> AcctInfo:
    return accts[1].address, accts[1].private_key, accts[1].signer


@pytest.fixture(scope="session")
def assets(creator_acct: AcctInfo, user_acct: AcctInfo) -> tuple[int, int]:
    addr, sk, _ = creator_acct
    user_addr, _, user_signer = user_acct

    sp = algod_client.suggested_params()
    txns: list[transaction.Transaction] = transaction.assign_group_id(
        [
            transaction.AssetCreateTxn(
                addr,
                sp,
                TOTAL_ASSET_TOKENS,
                0,
                default_frozen=False,
                asset_name="asset a",
                unit_name="A",
            ),
            transaction.AssetCreateTxn(
                addr,
                sp,
                TOTAL_ASSET_TOKENS,
                0,
                default_frozen=False,
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
    a_asset, b_asset = results[0]["asset-index"], results[1]["asset-index"]

    # Send some to the user account just to have them
    _opt_in_to_token(user_addr, user_signer, a_asset)
    _opt_in_to_token(user_addr, user_signer, b_asset)
    send_to_user_txns: list[transaction.Transaction] = transaction.assign_group_id(
        [
            transaction.AssetTransferTxn(
                addr, sp, user_addr, TOTAL_ASSET_TOKENS // 10, a_asset
            ),
            transaction.AssetTransferTxn(
                addr, sp, user_addr, TOTAL_ASSET_TOKENS // 10, b_asset
            ),
        ]
    )
    algod_client.send_transactions([txn.sign(sk) for txn in send_to_user_txns])

    return a_asset, b_asset


@pytest.fixture(scope="session")
def creator_app_client(creator_acct: AcctInfo) -> client.ApplicationClient:
    _, _, signer = creator_acct
    app_client = client.ApplicationClient(algod_client, amm.app, signer=signer)
    return app_client


def get_app_client_details(
    app_client: client.ApplicationClient,
) -> tuple[str, str, AccountTransactionSigner]:
    app_addr, addr, signer = (
        app_client.app_addr,
        app_client.sender,
        app_client.signer,
    )
    assert app_addr is not None
    assert addr is not None
    assert signer is not None
    assert isinstance(signer, AccountTransactionSigner)
    return app_addr, addr, signer


def test_app_create(creator_app_client: client.ApplicationClient) -> None:
    creator_app_client.create()
    global_state = creator_app_client.get_global_state()
    sender = creator_app_client.get_sender()

    assert global_state[amm.app.state.governor.str_key()] == _addr_to_hex(
        sender
    ), "The governor should be my address"
    assert global_state[amm.app.state.ratio.str_key()] == 0, "The ratio should be 0"


def minimum_fee_for_txn_count(
    sp: transaction.SuggestedParams, txn_count: int
) -> transaction.SuggestedParams:
    """
    Configures transaction fee _without_ considering network congestion.

    Since the function does not account for network congestion, do _not_ use the
    function as-is in a production use-case.
    """
    s = copy.deepcopy(sp)
    s.flat_fee = True
    s.fee = transaction.constants.min_txn_fee * txn_count
    return s


def assert_app_algo_balance(c: client.ApplicationClient, expected_algos: int) -> None:
    """
    Verifies the app's algo balance is not unexpectedly drained during
    app interaction (e.g. paying inner transaction fees).

    Due to the presence of rewards, the assertion tolerates actual > expected
    for small positive differences.
    """
    app_addr, _, _ = get_app_client_details(c)

    xs = helpers.get_balances(c.client, [app_addr])
    assert app_addr in xs
    assert 0 in xs[app_addr]
    actual_algos = xs[app_addr][0]

    # Before accounting for rewards, confirm algos were not drained.
    assert actual_algos >= expected_algos

    # Account for rewards. 0 in devmode
    micro_algos_tolerance = 10
    assert actual_algos - expected_algos <= micro_algos_tolerance


app_algo_balance: typing.Final = consts.algo * 10


def build_set_governor_transaction(new_governor: str) -> dict[str, typing.Any]:
    return {"new_governor": new_governor}


def build_boostrap_transaction(
    app_client: client.ApplicationClient, assets: tuple[int, int]
) -> dict[str, typing.Any]:

    app_addr, addr, signer = get_app_client_details(app_client)

    asset_a, asset_b = assets
    sp = app_client.client.suggested_params()

    return {
        "seed": TransactionWithSigner(
            txn=transaction.PaymentTxn(
                addr,
                sp,
                app_addr,
                app_algo_balance,
            ),
            signer=signer,
        ),
        "a_asset": asset_a,
        "b_asset": asset_b,
        "suggested_params": minimum_fee_for_txn_count(sp, 4),
    }


def build_mint_transaction(
    app_client: client.ApplicationClient,
    assets: tuple[int, int],
    pool_asset: int,
    a_amount: int,
    b_amount: int,
) -> dict[str, typing.Any]:

    app_addr, addr, signer = get_app_client_details(app_client)

    a_asset, b_asset = assets
    sp = app_client.get_suggested_params()

    return {
        "suggested_params": minimum_fee_for_txn_count(sp, 2),
        "a_xfer": TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, a_amount, a_asset),
            signer=signer,
        ),
        "b_xfer": TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, b_amount, b_asset),
            signer=signer,
        ),
        "pool_asset": pool_asset,
        "a_asset": a_asset,
        "b_asset": b_asset,
    }


def build_burn_transaction(
    app_client: client.ApplicationClient,
    assets: tuple[int, int],
    pool_asset: int,
    burn_amt: int,
) -> dict[str, typing.Any]:

    app_addr, addr, signer = get_app_client_details(app_client)

    sp = app_client.get_suggested_params()
    a_asset, b_asset = assets

    return {
        "suggested_params": minimum_fee_for_txn_count(sp, 3),
        "pool_xfer": TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, burn_amt, pool_asset),
            signer=signer,
        ),
        "pool_asset": pool_asset,
        "a_asset": a_asset,
        "b_asset": b_asset,
    }


def build_swap_transaction(
    app_client: client.ApplicationClient,
    assets: tuple[int, int],
    swap_amt: int,
    swap_asset: int | None = None,
) -> dict[str, typing.Any]:
    app_addr, addr, signer = get_app_client_details(app_client)

    sp = app_client.get_suggested_params()
    a_asset, b_asset = assets

    if swap_asset is None:
        swap_asset = a_asset

    return {
        "suggested_params": minimum_fee_for_txn_count(sp, 2),
        "swap_xfer": TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, swap_amt, swap_asset),
            signer=signer,
        ),
        "a_asset": a_asset,
        "b_asset": b_asset,
    }


def test_app_set_governor(
    creator_app_client: client.ApplicationClient, user_acct: AcctInfo
) -> None:
    _, creator_addr, _ = get_app_client_details(creator_app_client)

    user_addr, _, user_signer = user_acct

    state_before = creator_app_client.get_global_state()

    assert creator_addr is not None
    assert state_before[amm.app.state.governor.str_key()] == _addr_to_hex(creator_addr)

    # Set the new gov
    creator_app_client.call(
        "set_governor",
        **build_set_governor_transaction(user_addr),
    )

    state_after = creator_app_client.get_global_state()
    assert state_after[amm.app.state.governor.str_key()] == _addr_to_hex(user_addr)

    user_client = creator_app_client.prepare(signer=user_signer)
    # Return state to old gov
    user_client.call(
        "set_governor",
        **build_set_governor_transaction(creator_addr),
    )

    state_after_revert = creator_app_client.get_global_state()
    assert state_after_revert[amm.app.state.governor.str_key()] == _addr_to_hex(
        creator_addr
    )


def test_app_bootstrap(
    creator_app_client: client.ApplicationClient, assets: tuple[int, int]
) -> None:

    app_addr = creator_app_client.app_addr
    asset_a, asset_b = assets

    # Bootstrap to create pool token and set global state
    result = creator_app_client.call(
        "bootstrap",
        **build_boostrap_transaction(creator_app_client, assets),
    )

    assert_app_algo_balance(creator_app_client, app_algo_balance)

    pool_token = result.return_value
    assert pool_token > 0, "We should have created a pool token with asset id>0"

    # Check pool token params
    token_info = creator_app_client.client.asset_info(pool_token)
    assert isinstance(token_info, dict)
    assert token_info["params"]["name"] == "DPT-A-B"
    assert token_info["params"]["total"] == TOTAL_POOL_TOKENS
    assert token_info["params"]["reserve"] == app_addr
    assert token_info["params"]["manager"] == app_addr
    assert token_info["params"]["creator"] == app_addr

    # Make sure we're opted in
    ai = creator_app_client.get_application_account_info()
    assert len(ai["assets"]) == 3, "Should have 3 assets, A/B/Pool"

    # Make sure our state is updated
    global_state = creator_app_client.get_global_state()
    assert global_state[amm.app.state.pool_token.str_key()] == pool_token
    assert global_state[amm.app.state.asset_a.str_key()] == asset_a
    assert global_state[amm.app.state.asset_b.str_key()] == asset_b


def test_app_fund(creator_app_client: client.ApplicationClient) -> None:
    app_addr, addr, signer = get_app_client_details(creator_app_client)

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    _opt_in_to_token(addr, signer, pool_asset)

    balance_accts = [app_addr, addr]
    balances_before = helpers.get_balances(creator_app_client.client, balance_accts)

    a_amount = 10000
    b_amount = 3000

    creator_app_client.call(
        "mint",
        **build_mint_transaction(
            creator_app_client, (a_asset, b_asset), pool_asset, a_amount, b_amount
        ),
    )

    balances_after = helpers.get_balances(creator_app_client.client, balance_accts)
    balance_deltas = helpers.get_deltas(balances_before, balances_after)

    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    assert_app_algo_balance(creator_app_client, app_algo_balance)

    expected_pool_tokens = int((a_amount * b_amount) ** 0.5 - amm.SCALE)
    assert balance_deltas[addr][pool_asset] == expected_pool_tokens

    ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = int((a_amount * amm.SCALE) / b_amount)
    assert ratio == expected_ratio


def test_mint(creator_app_client: client.ApplicationClient) -> None:
    app_addr, addr, _ = get_app_client_details(creator_app_client)

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    balances_before = helpers.get_balances(creator_app_client.client, [app_addr, addr])

    ratio_before = _get_ratio_from_state(creator_app_client)

    a_amount = 40000
    b_amount = int(a_amount * amm.SCALE / ratio_before)

    creator_app_client.call(
        "mint",
        **build_mint_transaction(
            creator_app_client, (a_asset, b_asset), pool_asset, a_amount, b_amount
        ),
    )

    balances_after = helpers.get_balances(creator_app_client.client, [app_addr, addr])
    balance_deltas = helpers.get_deltas(balances_before, balances_after)

    # App got the right amount
    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    assert_app_algo_balance(creator_app_client, app_algo_balance)

    # We minted the correct amount of pool tokens
    issued = TOTAL_POOL_TOKENS - balances_before[app_addr][pool_asset]
    expected_pool_tokens = _get_tokens_to_mint(
        issued,
        a_amount,
        balances_before[app_addr][a_asset],
        b_amount,
        balances_before[app_addr][b_asset],
    )
    assert balance_deltas[addr][pool_asset] == int(expected_pool_tokens)

    # We updated the ratio accordingly
    actual_ratio = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert actual_ratio == expected_ratio


def test_burn(creator_app_client: client.ApplicationClient) -> None:
    app_addr, addr, _ = get_app_client_details(creator_app_client)
    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    assert addr
    balances_before = helpers.get_balances(creator_app_client.client, [app_addr, addr])

    burn_amt = balances_before[addr][pool_asset] // 10

    creator_app_client.call(
        "burn",
        **build_burn_transaction(
            creator_app_client, (a_asset, b_asset), pool_asset, burn_amt
        ),
    )

    balances_after = helpers.get_balances(creator_app_client.client, [app_addr, addr])
    balances_delta = helpers.get_deltas(balances_before, balances_after)

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


def test_swap(creator_app_client: client.ApplicationClient) -> None:
    app_addr, addr, _ = get_app_client_details(creator_app_client)

    _, a_asset, b_asset = _get_tokens_from_state(creator_app_client)

    balances_before = helpers.get_balances(creator_app_client.client, [app_addr, addr])

    swap_amt = balances_before[addr][a_asset] // 10
    creator_app_client.call(
        "swap",
        **build_swap_transaction(creator_app_client, (a_asset, b_asset), swap_amt),
    )

    balances_after = helpers.get_balances(creator_app_client.client, [app_addr, addr])
    balances_delta = helpers.get_deltas(balances_before, balances_after)

    assert balances_delta[app_addr][a_asset] == swap_amt

    # We minted the correct amount of pool tokens
    a_supply = balances_before[app_addr][a_asset]
    b_supply = balances_before[app_addr][b_asset]

    expected_b_tokens = _get_tokens_to_swap(swap_amt, a_supply, b_supply)
    assert balances_delta[addr][b_asset] == int(expected_b_tokens)

    assert_app_algo_balance(creator_app_client, app_algo_balance)

    ratio_after = _get_ratio_from_state(creator_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert ratio_after == expected_ratio


all_assert_groups = ["governor", "bootstrap", "mint", "burn", "swap"]


@pytest.fixture(
    scope="session",
    params=all_assert_groups,
)
def grouped_assert_cases(
    request: pytest.FixtureRequest,
    creator_app_client: client.ApplicationClient,
    user_acct: AcctInfo,
) -> list[AssertTestCase]:
    group: str = request.param
    return _assert_cases(group, creator_app_client, user_acct)


@pytest.fixture(scope="session")
def all_assert_cases(
    creator_app_client: client.ApplicationClient, user_acct: AcctInfo
) -> list[AssertTestCase]:
    return _assert_cases("all", creator_app_client, user_acct)


XS: typing.TypeAlias = list[tuple[str, dict[str, typing.Any]]]


def _assert_cases(
    group_key: str,
    creator_app_client: client.ApplicationClient,
    user_acct: AcctInfo,
) -> list[AssertTestCase]:
    def cases(
        m: abi.Method | pt.ABIReturnSubroutine | str,
        xs: XS,
        client: client.ApplicationClient = creator_app_client,
    ) -> list[AssertTestCase]:
        return [(a, m, txn, client) for a, txn in xs]

    fake_addr, _, fake_signer = user_acct
    fake_client = creator_app_client.prepare(signer=fake_signer, sender=fake_addr)

    _, addr, signer = get_app_client_details(creator_app_client)

    pool_asset, a_asset, b_asset = _get_tokens_from_state(creator_app_client)
    assets = (a_asset, b_asset)

    _opt_in_to_token(fake_addr, fake_signer, pool_asset)

    sp = creator_app_client.client.suggested_params()

    def add_txn(
        d: dict[str, AtomicTransactionComposer], key: str
    ) -> dict[str, AtomicTransactionComposer]:
        d[key] = AtomicTransactionComposer().add_transaction(
            TransactionWithSigner(
                txn=transaction.PaymentTxn(addr, sp, addr, 0),
                signer=signer,
            )
        )
        return d

    def wrong_receiver(
        d: dict[str, TransactionWithSigner], key: str
    ) -> dict[str, TransactionWithSigner]:
        typing.cast(transaction.AssetTransferTxn, d[key].txn).receiver = addr
        return d

    def override_pay_amount(
        d: dict[str, TransactionWithSigner], key: str, amt: int
    ) -> dict[str, TransactionWithSigner]:
        typing.cast(transaction.PaymentTxn, d[key].txn).amt = amt
        return d

    def override_axfer_amount(
        d: dict[str, TransactionWithSigner], key: str, amt: int
    ) -> dict[str, TransactionWithSigner]:
        typing.cast(transaction.AssetTransferTxn, d[key].txn).amount = amt
        return d

    def override_axfer_asset(
        d: dict[str, TransactionWithSigner], key: str, override: int
    ) -> dict[str, TransactionWithSigner]:
        typing.cast(transaction.AssetTransferTxn, d[key].txn).index = override
        return d

    def set_governor_cases() -> list[AssertTestCase]:
        def set_governor(new_gov: str) -> dict[str, typing.Any]:
            return build_set_governor_transaction(new_governor=new_gov)

        return cases(
            "set_governor",
            [("unauthorized", set_governor(addr))],
            fake_client,
        )

    def bootstrap_cases() -> list[AssertTestCase]:
        def bootstrap(
            app_client: client.ApplicationClient = creator_app_client,
            assets: tuple[int, int] = assets,
        ) -> dict[str, typing.Any]:
            return build_boostrap_transaction(app_client, assets)

        return cases(
            "bootstrap",
            [
                (
                    amm.Errors.GroupSizeNot2,
                    add_txn(bootstrap(), "atc"),
                ),
                (
                    amm.Errors.ReceiverNotAppAddr,
                    wrong_receiver(bootstrap(), "seed"),
                ),
                (
                    amm.Errors.AmountLessThanMinimum,
                    override_pay_amount(bootstrap(), "seed", int(consts.algo * 0.29)),
                ),
                (
                    amm.Errors.AssetIdsIncorrect,
                    bootstrap(assets=(b_asset, b_asset)),
                ),
            ],
        ) + cases("bootstrap", [("unauthorized", bootstrap())], fake_client)

    def mint_cases() -> list[AssertTestCase]:
        a_amt = 100000
        b_amt = a_amt // 10

        def mint(
            app_client: client.ApplicationClient = creator_app_client,
            assets: tuple[int, int] = assets,
            pool_asset: int = pool_asset,
            a_amount: int = a_amt,
            b_amount: int = b_amt,
        ) -> dict[str, typing.Any]:
            return build_mint_transaction(
                app_client, assets, pool_asset, a_amount, b_amount
            )

        well_formed_mint = cases(
            "mint",
            [
                (
                    amm.Errors.AssetAIncorrect,
                    mint(assets=(b_asset, b_asset)),
                ),
                (
                    amm.Errors.AssetBIncorrect,
                    mint(assets=(a_asset, a_asset)),
                ),
                (
                    amm.Errors.AssetPoolIncorrect,
                    mint(pool_asset=a_asset),
                ),
            ],
        ) + cases(
            "mint",
            [(amm.Errors.SenderInvalid, mint())],
            fake_client,
        )

        def valid_asset_xfer(key: str) -> XS:
            if key not in ["a_xfer", "b_xfer"]:
                raise Exception(f"Unexpected {key=}")

            return [
                (
                    amm.Errors.ReceiverNotAppAddr,
                    wrong_receiver(mint(), key),
                ),
                (
                    amm.Errors.AssetAIncorrect
                    if key == "a_xfer"
                    else amm.Errors.AssetBIncorrect,
                    override_axfer_asset(
                        mint(), key, b_asset if key == "a_xfer" else a_asset
                    ),
                ),
                (
                    amm.Errors.AmountLessThanMinimum,
                    override_axfer_amount(mint(), key, 0),
                ),
                (
                    amm.Errors.SendAmountTooLow,
                    override_axfer_amount(mint(), key, 1),
                ),
            ]

        valid_asset_a_xfer = cases("mint", valid_asset_xfer("a_xfer"))

        valid_asset_b_xfer = cases("mint", valid_asset_xfer("b_xfer"))

        return well_formed_mint + valid_asset_a_xfer + valid_asset_b_xfer

    def burn_cases() -> list[AssertTestCase]:
        def burn(
            app_client: client.ApplicationClient = creator_app_client,
            assets: tuple[int, int] = assets,
            pool_asset: int = pool_asset,
            burn_amt: int = 1,
        ) -> dict[str, typing.Any]:
            return build_burn_transaction(app_client, assets, pool_asset, burn_amt)

        well_formed_burn = cases(
            "burn",
            [
                (
                    amm.Errors.AssetPoolIncorrect,
                    burn(pool_asset=a_asset),
                ),
                (
                    amm.Errors.AssetAIncorrect,
                    burn(assets=(b_asset, b_asset)),
                ),
                (
                    amm.Errors.AssetBIncorrect,
                    burn(assets=(a_asset, a_asset)),
                ),
            ],
        )

        valid_pool_xfer = cases(
            "burn",
            [
                (
                    amm.Errors.ReceiverNotAppAddr,
                    wrong_receiver(burn(), "pool_xfer"),
                ),
                (amm.Errors.AmountLessThanMinimum, burn(burn_amt=0)),
                (
                    amm.Errors.AssetPoolIncorrect,
                    override_axfer_asset(burn(), "pool_xfer", a_asset),
                ),
            ],
        ) + cases(
            "burn",
            [(amm.Errors.SenderInvalid, burn())],
            fake_client,
        )

        return well_formed_burn + valid_pool_xfer

    def swap_cases() -> list[AssertTestCase]:
        def swap(
            app_client: client.ApplicationClient = creator_app_client,
            assets: tuple[int, int] = assets,
            swap_amt: int = 1,
            swap_asset: int = a_asset,
        ) -> dict[str, typing.Any]:
            return build_swap_transaction(app_client, assets, swap_amt, swap_asset)

        well_formed_swap = cases(
            "swap",
            [
                (
                    amm.Errors.AssetAIncorrect,
                    swap(assets=(b_asset, b_asset)),
                ),
                (
                    amm.Errors.AssetBIncorrect,
                    swap(assets=(a_asset, a_asset)),
                ),
            ],
        )

        valid_swap_xfer = cases(
            "swap",
            [
                (amm.Errors.AmountLessThanMinimum, swap(swap_amt=0)),
                (
                    amm.Errors.SendAmountTooLow,
                    swap(swap_amt=1),
                ),
                (
                    amm.Errors.AssetIdsIncorrect,
                    swap(swap_amt=0, swap_asset=pool_asset),
                ),
            ],
        ) + cases(
            "swap",
            [(amm.Errors.SenderInvalid, swap())],
            fake_client,
        )

        return well_formed_swap + valid_swap_xfer

    key_to_group: dict[str, list[AssertTestCase]] = {
        "governor": set_governor_cases(),
        "bootstrap": bootstrap_cases(),
        "mint": mint_cases(),
        "burn": burn_cases(),
        "swap": swap_cases(),
    }

    # Sanity check - Confirm additions to `key_to_group` are added
    # to fixture parameterization.
    assert sorted(key_to_group.keys()) == sorted(all_assert_groups)

    all_cases = list(itertools.chain.from_iterable(key_to_group.values()))
    return all_cases if group_key == "all" else key_to_group[group_key]


@dataclass
class ProgramAssertion:
    line: int
    message: str


def gather_asserts(program: str, src_map: SourceMap) -> dict[int, ProgramAssertion]:
    asserts: dict[int, ProgramAssertion] = {}

    program_lines = program.split("\n")
    for idx, line in enumerate(program_lines):
        # Take only the first chunk before spaces
        line, *_ = line.split(" ")
        if line != "assert":
            continue

        pcs = src_map.get_pcs_for_line(idx)
        if pcs is None:
            pc = 0
        else:
            pc = pcs[0]

        # TODO: this will be wrong for multiline comments
        line_before = program_lines[idx - 1]
        if not line_before.startswith("//"):
            continue

        asserts[pc] = ProgramAssertion(idx, line_before.strip("/ "))

    return asserts


def test_approval_asserts(grouped_assert_cases: list[AssertTestCase]) -> None:
    """
    Confirms each logical grouping of assertions raises the expected error message.
    """
    for msg, method, kwargs, app_client in grouped_assert_cases:
        with pytest.raises(LogicError, match=msg):
            app_client.call(method, **kwargs)


def test_approval_assert_coverage(
    all_assert_cases: list[AssertTestCase],
    creator_app_client: client.ApplicationClient,
) -> None:
    """
    Confirms `test_approval_asserts` exercises all app approval asserts.

    If `test_approval_asserts` passes and this test fails, it implies
    some asserts are _not_ tested.
    """

    assert creator_app_client.approval
    all_asserts = gather_asserts(
        creator_app_client.approval.teal, creator_app_client.approval.source_map
    )

    for msg, method, kwargs, app_client in all_assert_cases:
        with pytest.raises(LogicError, match=msg):
            try:
                app_client.call(method, **kwargs)
            except LogicError as e:
                if e.pc in all_asserts:
                    del all_asserts[e.pc]
                raise e

    assert len(all_asserts) == 0


def _get_tokens_to_mint(
    issued: int, a_amt: int, a_supply: int, b_amt: int, b_supply: int
) -> int:
    a_ratio = (a_amt * amm.SCALE) / a_supply
    b_ratio = (b_amt * amm.SCALE) / b_supply

    if a_ratio < b_ratio:
        return int((a_ratio * issued) / amm.SCALE)

    return int((b_ratio * issued) / amm.SCALE)


def _get_tokens_to_swap(in_amount: int, in_supply: int, out_supply: int) -> int:
    factor = amm.SCALE - amm.FEE
    return int(
        (in_amount * factor * out_supply)
        / ((in_supply * amm.SCALE) + (in_amount * factor))
    )


def _get_tokens_to_burn(asset_supply: int, burn_amount: int, pool_issued: int) -> int:
    return int((asset_supply * burn_amount) / pool_issued)


def _get_ratio_from_state(creator_app_client: client.ApplicationClient) -> int:
    global_state = creator_app_client.get_global_state()
    result = global_state[amm.app.state.ratio.str_key()]
    assert isinstance(result, int)
    return result


def _get_tokens_from_state(
    creator_app_client: client.ApplicationClient,
) -> tuple[int, int, int]:
    global_state = creator_app_client.get_global_state()
    return (
        int(global_state[amm.app.state.pool_token.str_key()]),
        int(global_state[amm.app.state.asset_a.str_key()]),
        int(global_state[amm.app.state.asset_b.str_key()]),
    )


def _expect_ratio(a_sup: int, b_sup: int) -> int:
    return int((a_sup * amm.SCALE) / b_sup)


def _opt_in_to_token(addr: str, signer: AccountTransactionSigner, id: int) -> None:
    sp = algod_client.suggested_params()
    atc = AtomicTransactionComposer()
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, addr, 0, id),
            signer=signer,
        )
    )
    atc.execute(algod_client, 2)


def _addr_to_hex(addr: str) -> str:
    return decode_address(addr).hex()


def test_demo() -> None:
    demo.main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(amm.app, dir_per_test_file=False)
