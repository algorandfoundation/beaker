from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    LogicSigTransactionSigner,
    TransactionWithSigner,
)
from algosdk.transaction import LogicSigAccount, PaymentTxn
from Cryptodome.Hash import keccak

import beaker
from beaker.precompile import PrecompiledLogicSignature

from examples.offload_compute import eth_checker


def main() -> None:
    algod_client = beaker.sandbox.get_algod_client()
    acct = beaker.sandbox.get_accounts().pop()

    # Create app client
    app_client = beaker.client.ApplicationClient(
        algod_client, eth_checker.app, signer=acct.signer
    )

    app_client.create()

    # Now we should have the approval program available
    assert app_client.approval and app_client.approval.teal is not None

    # Create a new app client with the lsig signer
    lsig_pc = PrecompiledLogicSignature(eth_checker.verify_lsig, algod_client)
    lsig_signer = LogicSigTransactionSigner(
        LogicSigAccount(lsig_pc.logic_program.raw_binary)
    )
    lsig_client = app_client.prepare(signer=lsig_signer)

    atc = AtomicTransactionComposer()

    # Add a payment just to cover fees
    sp_with_fees = algod_client.suggested_params()
    sp_with_fees.flat_fee = True
    sp_with_fees.fee = beaker.consts.milli_algo * 3
    atc.add_transaction(
        TransactionWithSigner(
            txn=PaymentTxn(acct.address, sp_with_fees, acct.address, 0),
            signer=acct.signer,
        )
    )

    message = b"OpenZeppelin"
    m = keccak.new(digest_bits=256)
    m.update(message)
    hash = m.digest()

    sp_no_fee = algod_client.suggested_params()
    sp_no_fee.flat_fee = True
    # V0
    hex_signature = (
        "5d99b6f7f6d1f73d1a26497f2b1c89b24c0993913f86e9a2d02cd69887d9c94f"
        + "3c880358579d811b21dd1b7fd9bb01c1d81d10e69f0384e675c32b39643be8921b"
    )
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        eth_checker.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    # V1
    hex_signature = (
        "331fe75a821c982f9127538858900d87d3ec1f9f737338ad67cad133fa48feff"
        + "48e6fa0c18abc62e42820f05943e47af3e9fbe306ce74d64094bdf1691ee53e01c"
    )
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        eth_checker.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    result = atc.execute(algod_client, 4)
    for rv in result.abi_results:
        print(rv.return_value)


if __name__ == "__main__":
    main()
