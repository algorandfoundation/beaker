import copy
from pathlib import Path

from pyteal import Expr

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
from beaker import client, sandbox, testing, consts
from beaker.client.application_client import ApplicationClient, ProgramAssertion
from beaker.client.logic_error import LogicException

from .amm import ConstantProductAMM, ConstantProductAMMErrors

accts = sandbox.get_accounts()
algod_client: AlgodClient = sandbox.get_algod_client()

TOTAL_POOL_TOKENS = 10000000000
TOTAL_ASSET_TOKENS = 10000000000

ARTIFACTS = Path.cwd() / "examples" / "amm" / "artifacts"


@pytest.fixture(scope="session")
def creator_acct() -> tuple[str, str, AccountTransactionSigner]:
    return accts[0].address, accts[0].private_key, accts[0].signer


@pytest.fixture(scope="session")
def user_acct() -> tuple[str, str, AccountTransactionSigner]:
    return accts[1].address, accts[1].private_key, accts[1].signer


@pytest.fixture(scope="session")
def assets(creator_acct, user_acct) -> tuple[int, int]:
    addr, sk, signer = creator_acct
    user_addr, user_sk, user_signer = user_acct

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

    return (a_asset, b_asset)


@pytest.fixture(scope="session")
def creator_app_client(creator_acct) -> client.ApplicationClient:
    _, _, signer = creator_acct
    app = ConstantProductAMM()
    app_client = client.ApplicationClient(algod_client, app, signer=signer)
    return app_client


@pytest.fixture(scope="session")
def CREATED_app_client(creator_app_client) -> client.ApplicationClient:
    creator_app_client.create()
    return creator_app_client


@pytest.fixture(scope="session")
def BOOTSTRAPPED_app_client(
    CREATED_app_client: client.ApplicationClient, assets: tuple[int, int]
) -> client.ApplicationClient:
    # Bootstrap to create pool token and set global state
    CREATED_app_client.call(
        ConstantProductAMM.bootstrap,
        **build_boostrap_transaction(CREATED_app_client, assets),
    )
    return CREATED_app_client


def minimum_fee_for_txn_count(
    sp: transaction.SuggestedParams, txn_count: int
) -> transaction.SuggestedParams:
    """
    Configures transaction fee _without_ considering network congestion.

    Since the function does not account for network congestion, do _not_ use the function as-is in a production use-case.
    """
    s = copy.deepcopy(sp)
    s.flat_fee = True
    s.fee = transaction.constants.min_txn_fee * txn_count
    return s


def assert_app_algo_balance(c: client.ApplicationClient, expected_algos: int):
    """
    Verifies the app's algo balance is not unexpectedly drained during app interaction (e.g. paying inner transaction fees).

    Due to the presence of rewards, the assertion tolerates actual > expected for small positive differences.
    """
    xs = testing.get_balances(c.client, [c.app_addr])
    assert c.app_addr in xs
    assert 0 in xs[c.app_addr]
    actual_algos = xs[c.app_addr][0]

    # Before accounting for rewards, confirm algos were not drained.
    assert actual_algos >= expected_algos

    # Account for rewards. 0 in devmode
    micro_algos_tolerance = 10
    assert actual_algos - expected_algos <= micro_algos_tolerance


app_algo_balance: typing.Final = consts.algo * 10


def build_boostrap_transaction(
    app_client: client.ApplicationClient, assets: tuple[int, int]
) -> dict[str, typing.Any]:

    app_addr, addr, signer = (
        app_client.app_addr,
        app_client.sender,
        app_client.signer,
    )

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
):

    app_addr, addr, signer = (
        app_client.app_addr,
        app_client.sender,
        app_client.signer,
    )

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
    app_client: ApplicationClient,
    assets: tuple[int, int],
    pool_asset: int,
    burn_amt: int,
):

    app_addr, addr, signer = (
        app_client.app_addr,
        app_client.sender,
        app_client.signer,
    )

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
    app_client: ApplicationClient,
    assets: tuple[int, int],
    pool_asset: int,
    swap_amt: int,
):
    app_addr, addr, signer = (
        app_client.app_addr,
        app_client.sender,
        app_client.signer,
    )

    sp = app_client.get_suggested_params()
    a_asset, b_asset = assets
    return {
        "suggested_params": minimum_fee_for_txn_count(sp, 2),
        "swap_xfer": TransactionWithSigner(
            txn=transaction.AssetTransferTxn(addr, sp, app_addr, swap_amt, a_asset),
            signer=signer,
        ),
        "pool_asset": pool_asset,
        "a_asset": a_asset,
        "b_asset": b_asset,
    }


def test_app_create(CREATED_app_client: client.ApplicationClient):
    app_state = CREATED_app_client.get_application_state()
    sender = CREATED_app_client.get_sender()

    assert (
        app_state[ConstantProductAMM.governor.str_key()] == decode_address(sender).hex()
    ), "The governor should be my address"
    assert app_state[ConstantProductAMM.ratio.str_key()] == 0, "The ratio should be 0"


def test_app_bootstrap(
    BOOTSTRAPPED_app_client: client.ApplicationClient, assets: tuple[int, int]
):

    app_addr = BOOTSTRAPPED_app_client.app_addr
    asset_a, asset_b = assets

    # Bootstrap to create pool token and set global state
    # result = BOOTSTRAPPED_app_client.call(
    #     ConstantProductAMM.bootstrap,
    #     **build_boostrap_transaction(BOOTSTRAPPED_app_client, assets),
    # )
    # pool_token = result.return_value

    assert_app_algo_balance(BOOTSTRAPPED_app_client, app_algo_balance)

    app_state = BOOTSTRAPPED_app_client.get_application_state()
    pool_token = app_state[ConstantProductAMM.pool_token.str_key()]

    assert pool_token > 0, "We should have created a pool token with asset id>0"

    # Check pool token params
    token_info = BOOTSTRAPPED_app_client.client.asset_info(pool_token)
    assert token_info["params"]["name"] == "DPT-A-B"
    assert token_info["params"]["total"] == TOTAL_POOL_TOKENS
    assert token_info["params"]["reserve"] == app_addr
    assert token_info["params"]["manager"] == app_addr
    assert token_info["params"]["creator"] == app_addr

    # Make sure we're opted in
    ai = BOOTSTRAPPED_app_client.get_application_account_info()
    assert len(ai["assets"]) == 3, "Should have 3 assets, A/B/Pool"

    # Make sure our state is updated
    assert app_state[ConstantProductAMM.asset_a.str_key()] == asset_a
    assert app_state[ConstantProductAMM.asset_b.str_key()] == asset_b


@pytest.fixture(scope="session")
def FUNDED_app_client(
    BOOTSTRAPPED_app_client: ApplicationClient,
) -> client.ApplicationClient:
    app_addr, addr, signer = (
        BOOTSTRAPPED_app_client.app_addr,
        BOOTSTRAPPED_app_client.sender,
        BOOTSTRAPPED_app_client.signer,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(BOOTSTRAPPED_app_client)

    assert addr
    _opt_in_to_token(addr, signer, pool_asset)

    balance_accts = [app_addr, addr]
    balances_before = testing.get_balances(
        BOOTSTRAPPED_app_client.client, balance_accts
    )

    a_amount = 10000
    b_amount = 3000

    BOOTSTRAPPED_app_client.call(
        ConstantProductAMM.mint,
        **build_mint_transaction(
            BOOTSTRAPPED_app_client, (a_asset, b_asset), pool_asset, a_amount, b_amount
        ),
    )

    balances_after = testing.get_balances(BOOTSTRAPPED_app_client.client, balance_accts)
    balance_deltas = testing.get_deltas(balances_before, balances_after)

    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    assert_app_algo_balance(BOOTSTRAPPED_app_client, app_algo_balance)

    expected_pool_tokens = int((a_amount * b_amount) ** 0.5 - ConstantProductAMM._scale)
    assert balance_deltas[addr][pool_asset] == expected_pool_tokens

    ratio = _get_ratio_from_state(BOOTSTRAPPED_app_client)
    expected_ratio = int((a_amount * ConstantProductAMM._scale) / b_amount)
    assert ratio == expected_ratio

    return BOOTSTRAPPED_app_client


def test_mint(FUNDED_app_client: ApplicationClient):
    app_addr, addr = (
        FUNDED_app_client.app_addr,
        FUNDED_app_client.sender,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(FUNDED_app_client)

    assert addr
    balances_before = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])

    ratio_before = _get_ratio_from_state(FUNDED_app_client)

    a_amount = 40000
    b_amount = int(a_amount * ConstantProductAMM._scale / ratio_before)

    FUNDED_app_client.call(
        ConstantProductAMM.mint,
        **build_mint_transaction(
            FUNDED_app_client, (a_asset, b_asset), pool_asset, a_amount, b_amount
        ),
    )

    balances_after = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])
    balance_deltas = testing.get_deltas(balances_before, balances_after)

    # App got the right amount
    assert balance_deltas[app_addr][a_asset] == a_amount
    assert balance_deltas[app_addr][b_asset] == b_amount
    assert_app_algo_balance(FUNDED_app_client, app_algo_balance)

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
    actual_ratio = _get_ratio_from_state(FUNDED_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert actual_ratio == expected_ratio


def test_burn(FUNDED_app_client: ApplicationClient):
    app_addr, addr = (
        FUNDED_app_client.app_addr,
        FUNDED_app_client.sender,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(FUNDED_app_client)

    assert addr
    balances_before = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])

    burn_amt = balances_before[addr][pool_asset] // 10

    FUNDED_app_client.call(
        ConstantProductAMM.burn,
        **build_burn_transaction(
            FUNDED_app_client, (a_asset, b_asset), pool_asset, burn_amt
        ),
    )

    balances_after = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])
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

    assert_app_algo_balance(FUNDED_app_client, app_algo_balance)

    ratio_after = _get_ratio_from_state(FUNDED_app_client)

    # Ratio should be identical?
    # assert ratio_before == ratio_after

    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert ratio_after == expected_ratio


def test_swap(FUNDED_app_client: ApplicationClient):
    app_addr, addr = (
        FUNDED_app_client.app_addr,
        FUNDED_app_client.sender,
    )

    pool_asset, a_asset, b_asset = _get_tokens_from_state(FUNDED_app_client)

    assert addr
    balances_before = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])

    swap_amt = balances_before[addr][a_asset] // 10
    FUNDED_app_client.call(
        ConstantProductAMM.swap,
        **build_swap_transaction(
            FUNDED_app_client, (a_asset, b_asset), pool_asset, swap_amt
        ),
    )

    balances_after = testing.get_balances(FUNDED_app_client.client, [app_addr, addr])
    balances_delta = testing.get_deltas(balances_before, balances_after)

    assert balances_delta[app_addr][a_asset] == swap_amt

    # We minted the correct amount of pool tokens
    a_supply = balances_before[app_addr][a_asset]
    b_supply = balances_before[app_addr][b_asset]

    expected_b_tokens = _get_tokens_to_swap(
        swap_amt, a_supply, b_supply, ConstantProductAMM._scale, ConstantProductAMM._fee
    )
    assert balances_delta[addr][b_asset] == int(expected_b_tokens)

    assert_app_algo_balance(FUNDED_app_client, app_algo_balance)

    ratio_after = _get_ratio_from_state(FUNDED_app_client)
    expected_ratio = _expect_ratio(
        balances_after[app_addr][a_asset], balances_after[app_addr][b_asset]
    )
    assert ratio_after == expected_ratio


def test_app_asserts(
    BOOTSTRAPPED_app_client: client.ApplicationClient,
    user_acct: tuple[str, str, AccountTransactionSigner],
):

    fake_addr, fake_pk, fake_signer = user_acct
    fake_client = BOOTSTRAPPED_app_client.prepare(signer=fake_signer, sender=fake_addr)

    app_addr, addr, signer = (
        BOOTSTRAPPED_app_client.app_addr,
        BOOTSTRAPPED_app_client.sender,
        BOOTSTRAPPED_app_client.signer,
    )

    assertion_triggers: list[tuple[str, str, typing.Any, dict[str, typing.Any]]] = []

    pool_asset, a_asset, b_asset = _get_tokens_from_state(BOOTSTRAPPED_app_client)
    assets = (a_asset, b_asset)

    # Bootstrap assertions

    sp = BOOTSTRAPPED_app_client.client.suggested_params()
    wrong_group_size_args = build_boostrap_transaction(BOOTSTRAPPED_app_client, assets)
    wrong_group_size_args["atc"] = AtomicTransactionComposer().add_transaction(
        TransactionWithSigner(
            txn=transaction.PaymentTxn(addr, sp, addr, 0),
            signer=signer,
        )
    )

    wrong_receiver_txn = build_boostrap_transaction(BOOTSTRAPPED_app_client, assets)
    wrong_receiver_txn["seed"].txn.receiver = addr

    wrong_seed_amount_txn = build_boostrap_transaction(BOOTSTRAPPED_app_client, assets)
    wrong_seed_amount_txn["seed"].txn.amt = int(consts.algo * 0.29)

    wrong_asset_ids = build_boostrap_transaction(BOOTSTRAPPED_app_client, assets)
    wrong_asset_ids["a_asset"], wrong_asset_ids["b_asset"] = (
        wrong_asset_ids["b_asset"],
        wrong_asset_ids["a_asset"],
    )

    assertion_triggers += [
        (
            ConstantProductAMMErrors.GroupSizeNot2,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.bootstrap,
            wrong_group_size_args,
        ),
        (
            ConstantProductAMMErrors.ReceiverNotAppAddr,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.bootstrap,
            wrong_receiver_txn,
        ),
        (
            ConstantProductAMMErrors.AmountLessThanMinimum,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.bootstrap,
            wrong_seed_amount_txn,
        ),
        (
            ConstantProductAMMErrors.AssetIdsIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.bootstrap,
            wrong_asset_ids,
        ),
    ]

    ####
    # Mint assertions
    ###

    a_amt = 100000
    b_amt = a_amt // 10

    mint_wrong_asset_a_in_reference = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_a_in_reference["a_asset"] = pool_asset

    mint_wrong_asset_b_in_reference = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_b_in_reference["b_asset"] = pool_asset

    mint_wrong_asset_pool_in_reference = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_pool_in_reference["pool_asset"] = a_asset

    assertion_triggers += [
        (
            ConstantProductAMMErrors.AssetAIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_a_in_reference,
        ),
        (
            ConstantProductAMMErrors.AssetBIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_b_in_reference,
        ),
        (
            ConstantProductAMMErrors.AssetPoolIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_pool_in_reference,
        ),
    ]

    mint_wrong_asset_a_receiver = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_a_receiver["a_xfer"].txn.receiver = addr

    mint_wrong_asset_a_id = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_a_id["a_xfer"].txn.index = b_asset

    mint_wrong_asset_a_amount = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_a_amount["a_xfer"].txn.amount = 0

    mint_wrong_asset_a_sender = build_mint_transaction(
        fake_client, assets, pool_asset, a_amt, b_amt
    )

    assertion_triggers += [
        (
            ConstantProductAMMErrors.ReceiverNotAppAddr,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_a_receiver,
        ),
        (
            ConstantProductAMMErrors.AssetAIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_a_id,
        ),
        (
            ConstantProductAMMErrors.AmountLessThanMinimum,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_a_amount,
        ),
        (
            ConstantProductAMMErrors.SenderInvalid,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_a_sender,
        ),
    ]

    mint_wrong_asset_b_receiver = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_b_receiver["b_xfer"].txn.receiver = addr

    mint_wrong_asset_b_id = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_b_id["b_xfer"].txn.index = a_asset

    mint_wrong_asset_b_amount = build_mint_transaction(
        BOOTSTRAPPED_app_client, assets, pool_asset, a_amt, b_amt
    )
    mint_wrong_asset_b_amount["b_xfer"].txn.amount = 0

    mint_wrong_asset_b_sender = build_mint_transaction(
        fake_client, assets, pool_asset, a_amt, b_amt
    )

    assertion_triggers += [
        (
            ConstantProductAMMErrors.ReceiverNotAppAddr,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_b_receiver,
        ),
        (
            ConstantProductAMMErrors.AssetBIncorrect,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_b_id,
        ),
        (
            ConstantProductAMMErrors.AmountLessThanMinimum,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_b_amount,
        ),
        (
            ConstantProductAMMErrors.SenderInvalid,
            "Assert(cond, comment=cmt)",
            ConstantProductAMM.mint,
            mint_wrong_asset_b_sender,
        ),
    ]

    # TODO: rest of them

    all_asserts: dict[int, ProgramAssertion] = BOOTSTRAPPED_app_client.approval_asserts  # type: ignore[assignment]
    for msg, pyteal_reversed, method, kwargs in assertion_triggers:
        print(f"Testing {msg}")
        with pytest.raises(LogicException, match=msg):
            try:
                BOOTSTRAPPED_app_client.call(method, **kwargs)
            except LogicException as e:
                assert pyteal_reversed in str(e)
                if e.pc in all_asserts:
                    del all_asserts[e.pc]
                raise e

    print(f"Unhandled asserts ({len(all_asserts)}): {all_asserts}")


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
        int(app_state[ConstantProductAMM.pool_token.str_key()]),
        int(app_state[ConstantProductAMM.asset_a.str_key()]),
        int(app_state[ConstantProductAMM.asset_b.str_key()]),
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


def test_sourcemap(CREATED_app_client: client.ApplicationClient):
    CREATED_app_client.build()
    pt_approval_sourcemap = CREATED_app_client.app.pyteal_approval_sourcemap
    pt_clear_source_map = CREATED_app_client.app.pyteal_clear_sourcemap

    assert pt_approval_sourcemap
    assert pt_clear_source_map

    with open(ARTIFACTS / "approval_sourcemap.teal", "w") as f:
        # TODO: should default to the following and hence avoid the params
        annotated = pt_approval_sourcemap.annotated_teal(
            unparse_hybrid=True, concise=False
        )
        f.write(annotated)

    with open(ARTIFACTS / "clear_sourcemap.teal", "w") as f:
        # TODO: should default to the following and hence avoid the params
        annotated = pt_clear_source_map.annotated_teal(
            unparse_hybrid=True, concise=False
        )
        f.write(annotated)
