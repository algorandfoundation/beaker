import pytest
from typing import cast
from algosdk.constants import ZERO_ADDRESS
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    AccountTransactionSigner,
    TransactionWithSigner,
)
from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.encoding import decode_address
from beaker import client, sandbox, testing, consts
from beaker.client.logic_error import LogicException

from .arc18 import ARC18


@pytest.fixture(scope="session")
def accts():
    return sandbox.get_accounts()


@pytest.fixture(scope="session")
def algod_client() -> AlgodClient:
    return sandbox.get_algod_client()


@pytest.fixture(scope="session")
def creator_acct(
    accts: list[sandbox.SandboxAccount],
) -> tuple[str, str, AccountTransactionSigner]:
    return (accts[0].address, accts[0].private_key, accts[0].signer)


@pytest.fixture(scope="session")
def buyer_acct(
    accts: list[sandbox.SandboxAccount],
) -> tuple[str, str, AccountTransactionSigner]:
    return (accts[1].address, accts[1].private_key, accts[1].signer)


@pytest.fixture(scope="session")
def royalty_acct(
    accts: list[sandbox.SandboxAccount],
) -> tuple[str, str, AccountTransactionSigner]:
    return (accts[2].address, accts[2].private_key, accts[2].signer)


@pytest.fixture(scope="session")
def payment_asset(creator_acct, algod_client: AlgodClient) -> int:
    addr, sk, _ = creator_acct
    sp = algod_client.suggested_params()
    txn = transaction.AssetCreateTxn(
        addr,
        sp,
        1000000,
        0,
        False,
        asset_name="Conch Shells",
        unit_name="cshell",
    )
    txid = algod_client.send_transaction(txn.sign(sk))
    result = transaction.wait_for_confirmation(algod_client, txid, 4)
    return result["asset-index"]


@pytest.fixture(scope="session")
def app_client(creator_acct, algod_client: AlgodClient) -> client.ApplicationClient:
    _, _, signer = creator_acct
    app = ARC18()
    app_client = client.ApplicationClient(algod_client, app, signer=signer)
    app_client.create()
    app_client.fund(1 * consts.algo)
    app_client.opt_in()
    return app_client


@pytest.fixture(scope="session")
def royalty_asset(
    app_client: client.ApplicationClient, buyer_acct, algod_client: AlgodClient
) -> int:
    sp = algod_client.suggested_params()
    atc = AtomicTransactionComposer()
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetCreateTxn(
                app_client.get_sender(),
                sp,
                1,
                0,
                True,
                asset_name="Test NFT",
                unit_name="tstnft",
                clawback=app_client.app_addr,
                freeze=app_client.app_addr,
                manager=app_client.app_addr,
                reserve=app_client.app_addr,
            ),
            signer=app_client.signer,
        )
    )
    result = atc.execute(app_client.client, 4)
    result = transaction.wait_for_confirmation(app_client.client, result.tx_ids[0], 4)
    royalty_asset_id = result["asset-index"]

    buyer_addr, buyer_sk, buyer_signer = buyer_acct
    sp = app_client.client.suggested_params()
    atc = AtomicTransactionComposer()
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.AssetOptInTxn(buyer_addr, sp, royalty_asset_id),
            signer=buyer_signer,
        )
    )
    atc.execute(app_client.client, 4)

    return royalty_asset_id


def test_app_created(app_client: client.ApplicationClient):
    app_state = app_client.get_application_state()
    sender = app_client.get_sender()
    assert (
        app_state[ARC18.administrator.str_key()] == decode_address(sender).hex()
    ), "The administrator should be my address"


def test_set_administrator(app_client: client.ApplicationClient, buyer_acct):
    app = cast(ARC18, app_client.app)
    addr = app_client.get_sender()

    buyer_addr, _, buyer_signer = buyer_acct

    app_client.call(app.set_administrator, new_admin=buyer_addr)
    state = app_client.get_application_state()
    assert (
        state[ARC18.administrator.str_key()] == decode_address(buyer_addr).hex()
    ), "Expected new admin to be addr passed"

    result = app_client.call(app.get_administrator)
    assert buyer_addr == result.return_value, "Admin should be set to buyer_addr"

    with pytest.raises(Exception):
        app_client.call(app.set_administrator, new_admin=buyer_addr)

    buyer_client = app_client.prepare(signer=buyer_signer)
    buyer_client.call(app.set_administrator, new_admin=addr)
    state = app_client.get_application_state()
    assert (
        state[ARC18.administrator.str_key()] == decode_address(addr).hex()
    ), "Expected new admin to be addr passed"

    with pytest.raises(Exception):
        buyer_client.call(app.set_administrator, new_admin=addr)


def test_set_policy(app_client: client.ApplicationClient, royalty_acct):
    app = cast(ARC18, app_client.app)

    rcv_addr, rcv_sk, rcv_signer = royalty_acct
    basis = 100

    app_client.call(app.set_policy, royalty_policy=[rcv_addr, basis])
    state = app_client.get_application_state()
    assert (
        state[ARC18.royalty_basis.str_key()] == basis
    ), "Expected royalty basis to match what we passed in"
    assert (
        state[ARC18.royalty_receiver.str_key()] == decode_address(rcv_addr).hex()
    ), "Expected royalty receiver to match what we passed in"

    result = app_client.call(app.get_policy)
    policy = result.return_value
    assert policy[0] == rcv_addr, "Royalty receiver should equal rcv_addr"
    assert policy[1] == basis, "Royalty basis should equal basis"

    with pytest.raises(Exception):
        app_client.call(
            app.set_policy,
            royalty_policy=[
                rcv_addr,
                ARC18._basis_point_multiplier + 1,
            ],
        )

    with pytest.raises(Exception):
        app_client.call(app.set_policy, royalty_policy=["", basis])


def test_set_payment_asset(app_client: client.ApplicationClient, payment_asset: int):
    app = cast(ARC18, app_client.app)

    sp = app_client.client.suggested_params()
    sp.flat_fee = True
    sp.fee = sp.min_fee * 2

    app_client.call(
        app.set_payment_asset,
        suggested_params=sp,
        payment_asset=payment_asset,
        is_allowed=True,
    )
    info = app_client.get_application_account_info()
    balances = testing.balances(info)
    assert balances[payment_asset] == 0, "We've opted into the payment asset"

    app_client.call(
        app.set_payment_asset,
        suggested_params=sp,
        payment_asset=payment_asset,
        is_allowed=False,
    )
    info = app_client.get_application_account_info()
    balances = testing.balances(info)
    assert payment_asset not in balances, "We've opted out of the payment asset"


def test_offer(app_client: client.ApplicationClient, royalty_asset: int):
    app = cast(ARC18, app_client.app)
    addr = app_client.sender

    amt = 1
    auth = addr

    app_client.call(
        app.offer,
        royalty_asset=royalty_asset,
        offer=[auth, amt],
        previous_offer=[ZERO_ADDRESS, 0],
    )

    acct_state = app_client.get_account_state(raw=True)

    key_bytes = royalty_asset.to_bytes(8, "big")
    amt_bytes = amt.to_bytes(8, "big")
    auth_bytes = decode_address(auth)

    assert acct_state[key_bytes] == auth_bytes + amt_bytes

    result = app_client.call(app.get_offer, royalty_asset=royalty_asset, owner=addr)
    offer = result.return_value
    assert offer[0] == auth, "Offered auth should equal addr"
    assert offer[1] == amt, "Offered amount should equal amount"

    try:
        # Wrong address
        app_client.call(
            app.offer,
            royalty_asset=royalty_asset,
            offer=[auth, amt],
            previous_offer=[ZERO_ADDRESS, 1],
        )
    except LogicException as le:
        # TODO: get _actual_ assert from pyteal with message
        # assert le.assert_comment == "wrong address"
        assert le.msg.startswith("assert failed")

    try:
        # Wrong amount
        app_client.call(
            app.offer,
            royalty_asset=royalty_asset,
            offer=[auth, amt],
            previous_offer=[auth, 0],
        )
    except LogicException as le:
        # assert le.assert_comment == "wrong amount"
        assert le.msg.startswith("assert failed")


def test_transfer_algo_payment(
    app_client: client.ApplicationClient, royalty_asset: int, buyer_acct, royalty_acct
):
    app, addr, app_addr = (
        cast(ARC18, app_client.app),
        app_client.get_sender(),
        app_client.app_addr,
    )

    buyer_addr, _, buyer_signer = buyer_acct
    rcv_addr, _, _ = royalty_acct

    balance_accts = [addr, buyer_addr, app_addr, rcv_addr]
    balance_before = testing.get_balances(app_client.client, balance_accts)

    amt = 1
    payment_amt = 5 * consts.algo

    pay_sp = app_client.client.suggested_params()
    pay_sp.flat_fee = True
    pay_sp.fee = pay_sp.min_fee * 5

    auth_sp = app_client.client.suggested_params()
    auth_sp.flat_fee = True
    auth_sp.fee = 0

    app_client.call(
        app.transfer_algo_payment,
        suggested_params=auth_sp,
        royalty_asset=royalty_asset,
        royalty_asset_amount=1,
        owner=addr,
        buyer=buyer_addr,
        royalty_receiver=rcv_addr,
        payment_txn=TransactionWithSigner(
            txn=transaction.PaymentTxn(
                buyer_addr, pay_sp, app_client.app_addr, payment_amt
            ),
            signer=buyer_signer,
        ),
        offered_amt=amt,
    )

    balance_after = testing.get_balances(app_client.client, balance_accts)
    deltas = testing.get_deltas(balance_before, balance_after)

    royalty_amt = payment_amt / 100

    assert deltas[app_client.app_addr][0] == 0, "App should not change algo balance"
    assert (
        deltas[addr][0] == payment_amt - royalty_amt
    ), "Owner should receive payment - royalty amt"

    assert deltas[buyer_addr][0] == -(
        payment_amt + pay_sp.fee
    ), "Buyer should have paid full payment + any fees"
    assert (
        deltas[rcv_addr][0] == royalty_amt
    ), "Royalty receiver should have gotten share of royalty"


def test_transfer_asset_payment(app_client: client.ApplicationClient):
    pass


def test_transfer_royalty_free_move(app_client: client.ApplicationClient):
    pass
