import pytest
import pyteal as pt
from base64 import b64decode

from algosdk.account import generate_account
from algosdk.logic import get_application_address
from algosdk.future.transaction import Multisig, LogicSigAccount
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    MultisigTransactionSigner,
    LogicSigTransactionSigner,
)

from ..sandbox import get_accounts, get_client
from ..application import Application
from ..application_schema import ApplicationStateValue, AccountStateValue
from .application_client import ApplicationClient


class App(Application):
    app_state_val_int = ApplicationStateValue(pt.TealType.uint64)
    app_state_val_byte = ApplicationStateValue(pt.TealType.bytes)
    acct_state_val_int = AccountStateValue(pt.TealType.uint64)
    acct_state_val_byte = AccountStateValue(pt.TealType.bytes)


def test_app_client_create():
    app = App()
    client = get_client()
    ac = ApplicationClient(client, app)
    assert ac.signer == None, "Should not have a signer"
    assert ac.sender == None, "Should not have a sender"
    assert ac.app_id == 0, "Should not have app id"
    assert ac.app_addr == None, "Should not have app address"
    assert ac.suggested_params == None, "Should not have suggested params"

    with pytest.raises(Exception):
        ac.get_signer(None)

    with pytest.raises(Exception):
        ac.get_sender(None, None)


def test_app_prepare():
    app = App()
    client = get_client()

    addr, private_key = get_accounts()[0]
    signer = AccountTransactionSigner(private_key=private_key)

    ac_with_signer = ApplicationClient(client, app, signer=signer)

    assert ac_with_signer.signer == signer, "Should have the same signer"
    assert ac_with_signer.sender == None, "Should not have a sender"

    assert ac_with_signer.get_signer(None) == signer, "Should produce the same signer"
    assert (
        ac_with_signer.get_sender(None, None) == addr
    ), "Should produce the same address"

    new_pk, new_addr = generate_account()
    new_signer = AccountTransactionSigner(new_pk)
    ac_with_signer_and_sender = ac_with_signer.prepare(sender=new_addr)

    assert (
        ac_with_signer_and_sender.signer == signer
    ), "Should have the same original signer"
    assert ac_with_signer_and_sender.sender == new_addr, "Should not have a sender"

    assert (
        ac_with_signer_and_sender.get_signer(None) == signer
    ), "Should produce the same signer"
    assert (
        ac_with_signer_and_sender.get_sender(None, None) == new_addr
    ), "Should produce the new address"

    assert (
        ac_with_signer_and_sender.get_signer(new_signer) == new_signer
    ), "Should be new signer"
    assert (
        ac_with_signer_and_sender.get_sender(None, new_signer) == new_addr
    ), "Should be new address"

    accts = [generate_account() for _ in range(3)]
    addrs = [acct[1] for acct in accts]
    sks = [acct[0] for acct in accts]

    msig_acct = Multisig(1, 3, addrs)
    msts = MultisigTransactionSigner(msig_acct, sks[0])

    ac_with_msig = ac_with_signer.prepare(signer=msts)
    assert ac_with_msig.signer == msts, "Should have the same signer"
    assert (
        ac_with_msig.sender == msig_acct.address()
    ), "Should have the address of the msig as the sender"
    assert ac_with_msig.get_signer(None) == msts, "Should produce the same signer"
    assert (
        ac_with_msig.get_sender(None, None) == msig_acct.address()
    ), "Should produce the same address"

    # pragma version 6; int 1; return
    program = b64decode("BoEBQw==")
    lsig = LogicSigAccount(program)
    lsig_signer = LogicSigTransactionSigner(lsig)

    ac_with_lsig = ac_with_signer.prepare(signer=lsig_signer)
    assert ac_with_lsig.signer == lsig_signer, "Should have the same signer"
    assert (
        ac_with_lsig.sender == lsig.address()
    ), "Should have the address of the lsig as the sender"
    assert (
        ac_with_lsig.get_signer(None) == lsig_signer
    ), "Should produce the same signer"
    assert (
        ac_with_lsig.get_sender(None, None) == lsig.address()
    ), "Should produce the same address"

    ac_with_app_id = ac_with_signer.prepare(app_id=3)
    assert (
        ac_with_signer.app_id == 0
    ), "We should not have changed the app id in the original"
    assert (
        ac_with_app_id.app_id == 3
    ), "We should have overwritten the app id in the new version"


def test_compile():
    version = 5
    app = App(version=version)
    client = get_client()
    ac = ApplicationClient(client, app)

    approval_program = ac.compile_approval()
    assert len(approval_program) > 0, "Should have a valid approval program"
    assert approval_program[0] == version, "First byte should be the version we set"

    clear_program = ac.compile_clear()
    assert len(clear_program) > 0, "Should have a valid clear program"
    assert clear_program[0] == version, "First byte should be the version we set"


def test_create():
    app = App()
    accts = get_accounts()

    addr, pk = accts.pop()
    signer = AccountTransactionSigner(pk)

    client = get_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, app_addr, tx_id = ac.create()
    assert app_id > 0
    assert app_addr == get_application_address(app_id)
    assert ac.app_id == app_id
    assert ac.app_addr == app_addr

    result_tx = client.pending_transaction_info(tx_id)
    assert result_tx["application-index"] == app_id
    assert result_tx["confirmed-round"] > 0
    assert result_tx["pool-error"] == ""
    txn = result_tx["txn"]["txn"]
    assert txn["snd"] == addr
    assert txn['apgs'] == {'nbs': 1, 'nui': 1}
    assert txn['apls'] == {'nbs': 1, 'nui': 1}

    new_addr, new_pk = accts.pop()
    new_signer = AccountTransactionSigner(new_pk)
    new_ac = ac.prepare(signer=new_signer)
    extra_pages = 2
    sp = client.suggested_params()
    sp.fee = 1_000_000
    sp.flat_fee = True
    app_id, app_addr, tx_id = new_ac.create(
        extra_pages=extra_pages, suggested_params=sp
    )
    assert app_id > 0
    assert app_addr == get_application_address(app_id)
    assert new_ac.app_id == app_id
    assert new_ac.app_addr == app_addr

    result_tx = client.pending_transaction_info(tx_id)
    assert result_tx["application-index"] == app_id
    assert result_tx["confirmed-round"] > 0
    assert result_tx["pool-error"] == ""
    txn = result_tx["txn"]["txn"]
    assert txn["snd"] == new_addr
    assert txn["apep"] == extra_pages
    assert txn["fee"] == sp.fee
    assert txn['apgs'] == {'nbs': 1, 'nui': 1}
    assert txn['apls'] == {'nbs': 1, 'nui': 1}


def test_update():

    pass


def test_delete():
    pass


def test_opt_in():
    pass


def test_close_out():
    pass


def test_clear_state():
    pass


def test_call():
    pass


def test_add_method_call():
    pass


def test_resolve():
    pass
