from pathlib import Path

from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk.v2client.algod import AlgodClient

from beaker import client, sandbox
from .amm import ConstantProductAMM

accts = sandbox.get_accounts()
algod_client: AlgodClient = sandbox.get_algod_client()

ARTIFACTS = Path.cwd() / "examples" / "amm" / "artifacts"


def test_sourcemap():
    creator_acct: tuple[str, str, AccountTransactionSigner]
    creator_app_client: client.ApplicationClient

    creator_acct = accts[0].address, accts[0].private_key, accts[0].signer

    _, _, signer = creator_acct
    app = ConstantProductAMM()
    creator_app_client = client.ApplicationClient(algod_client, app, signer=signer)

    creator_app_client.build()

    annotated_approval = creator_app_client.app.annotated_approval_program
    annotated_clear = creator_app_client.app.annotated_clear_program
    assert annotated_approval
    assert annotated_clear

    pt_approval_sourcemap = creator_app_client.app.pyteal_approval_sourcemap
    pt_clear_sourcemap = creator_app_client.app.pyteal_clear_sourcemap
    assert pt_approval_sourcemap
    assert pt_clear_sourcemap

    assert annotated_approval == pt_approval_sourcemap.annotated_teal(
        omit_headers=False, concise=False
    )
    assert annotated_clear == pt_clear_sourcemap.annotated_teal(
        omit_headers=False, concise=False
    )

    with open(ARTIFACTS / "approval_sourcemap.teal", "w") as f:
        f.write(annotated_approval)

    with open(ARTIFACTS / "clear_sourcemap.teal", "w") as f:
        f.write(annotated_clear)
