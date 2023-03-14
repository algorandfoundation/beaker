import base64
from copy import copy

from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    LogicSigTransactionSigner,
    TransactionWithSigner,
)
from algosdk.encoding import decode_address
from algosdk.transaction import LogicSigAccount
from nacl.signing import SigningKey

from beaker import client, consts, sandbox
from beaker.precompile import PrecompiledLogicSignatureTemplate

from examples.templated_lsig import sig_checker


def sign_msg(msg: str, sk: str) -> bytes:
    """utility function for signing arbitrary data"""
    pk = list(base64.b64decode(sk))
    return SigningKey(bytes(pk[:32])).sign(msg.encode()).signature


def main() -> None:
    acct = sandbox.get_accounts().pop()

    # Create app client
    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), sig_checker.app, signer=acct.signer
    )

    # deploy app
    app_client.create()

    # Get the signer for the lsig from its populated precompile
    lsig_pc = PrecompiledLogicSignatureTemplate(sig_checker.lsig, app_client.client)
    lsig_signer = LogicSigTransactionSigner(
        LogicSigAccount(
            lsig_pc.populate_template(user_addr=decode_address(acct.address))
        )
    )
    # Prepare a new client so it can sign calls
    lsig_client = app_client.prepare(signer=lsig_signer)

    atc = AtomicTransactionComposer()

    # Create a dummy transaction to cover fees (still cheaper than multiple app calls)
    sp = app_client.client.suggested_params()
    covering_sp = copy(sp)
    covering_sp.flat_fee = True
    covering_sp.fee = 2 * consts.milli_algo
    atc.add_transaction(
        TransactionWithSigner(
            txn=transaction.PaymentTxn(acct.address, covering_sp, acct.address, 0),
            signer=acct.signer,
        )
    )

    # Message to sign
    msg = "Sign me please"
    # Signature
    sig = sign_msg(msg, acct.signer.private_key)

    # Since we dont fund this account, just set its fees to 0
    free_sp = copy(sp)
    free_sp.flat_fee = True
    free_sp.fee = 0

    # Add the call to the `check` method to be signed by the populated template logic
    lsig_client.add_method_call(
        atc,
        sig_checker.check,
        suggested_params=free_sp,
        signer_address=acct.address,
        msg=msg,
        sig=sig,
    )

    # run it
    result = atc.execute(app_client.client, 4)
    print(f"Confirmed in round {result.confirmed_round}")


if __name__ == "__main__":
    main()
