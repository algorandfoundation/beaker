import random
import string
import typing

from algosdk import transaction as txns
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    LogicSigTransactionSigner,
)

import beaker
from beaker.precompile import PrecompiledLogicSignatureTemplate

from examples.account_storage import disk_hungry


def get_nonce(n: int = 10) -> str:
    return "".join(random.choice(string.ascii_uppercase) for _ in range(n))


def create_and_opt_in_account(
    app_client: beaker.client.ApplicationClient,
    lsig_template: PrecompiledLogicSignatureTemplate,
) -> str:
    nonce = get_nonce()

    # Populate the binary template with the random nonce and get back
    # a Signer obj to submit transactions
    lsig_signer = LogicSigTransactionSigner(
        txns.LogicSigAccount(lsig_template.populate_template(nonce=nonce))
    )

    lsig_address = lsig_signer.lsig.address()
    print(f"Creating templated lsig with nonce {nonce} and address {lsig_address}")

    atc = AtomicTransactionComposer()

    # Give the lsig 2 algo for min balance (More than needed)
    app_client.add_transaction(
        atc,
        txns.PaymentTxn(
            sender=app_client.sender,
            sp=app_client.get_suggested_params(),
            receiver=lsig_address,
            amt=2 * beaker.consts.algo,
        ),
    )

    # Add opt in method call on behalf of lsig
    app_client.add_method_call(
        atc,
        disk_hungry.add_account,
        signer=lsig_signer,
        nonce=nonce.encode(),
        rekey_to=app_client.app_addr,
        on_complete=txns.OnComplete.OptInOC,
    )

    # Run it
    app_client.execute_atc(atc)

    return lsig_address


def main() -> None:
    # Create app client
    app_client = beaker.client.ApplicationClient(
        client=beaker.sandbox.get_algod_client(),
        app=disk_hungry.app,
        signer=beaker.sandbox.get_accounts().pop().signer,
    )

    # Deploy the app
    app_client.create()

    lsig_pc = PrecompiledLogicSignatureTemplate(disk_hungry.key_sig, app_client.client)
    # Create 10 random nonces for unique lsig accounts
    # and make them opt in to the app
    for _ in range(10):
        # Create the account and opt it into the app, also rekeys it to the app address
        lsig_address = create_and_opt_in_account(app_client, lsig_pc)

        # Max is 8 (bits per byte) * 127 (bytes per key) * 16 (max keys) == 16256
        idx = 16255
        app_client.call(disk_hungry.flip_bit, nonce_acct=lsig_address, bit_idx=idx)

        # Get the full state for the lsig we used to store this bit
        acct_state = app_client.get_local_state(lsig_address, raw=True)

        # Make sure the blob is in the right order
        blob = b"".join(
            [typing.cast(bytes, acct_state[x.to_bytes(1, "big")]) for x in range(16)]
        )

        # Did the expected byte have the expected integer value?
        assert int(blob[idx // 8]) == 2 ** (idx % 8)
        print(f"bit set correctly at index {idx}")


if __name__ == "__main__":
    main()
