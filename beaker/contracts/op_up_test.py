from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.future.transaction import PaymentTxn
from beaker.client import ApplicationClient
from beaker.contracts.op_up import OpUp
from beaker.consts import milli_algo
from beaker.sandbox import get_algod_client, get_accounts


def test_op_up():
    app = OpUp()

    acct = get_accounts().pop()

    client = get_algod_client()

    ac = ApplicationClient(client, app, signer=acct.signer)

    _, app_addr, _ = ac.create()

    sp = client.suggested_params()
    sp.flat_fee = True
    sp.fee = 256 * milli_algo
    ptxn = TransactionWithSigner(
        txn=PaymentTxn(acct.address, sp, app_addr, int(1e6)), signer=acct.signer
    )

    result = ac.call(app.opup_bootstrap, ptxn=ptxn)
    created_app_id = result.return_value
    assert created_app_id > 0

    app_acct_info = ac.get_application_account_info()
    assert len(app_acct_info["created-apps"]) == 1

    state = ac.get_application_state()
    assert state["ouaid"] == created_app_id
