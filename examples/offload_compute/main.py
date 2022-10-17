from typing import Final, cast
from Cryptodome.Hash import keccak
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.future.transaction import *

from pyteal import *
from beaker import *
from beaker.precompile import LSigPrecompile

if __name__ == "__main__":
    from lsig import EthEcdsaVerify, HashValue, Signature
else:
    from .lsig import EthEcdsaVerify, HashValue, Signature


class EthChecker(Application):

    # The lsig that will be responsible for validating the
    # incoming signature against the incoming hash
    # When passed to Precompile, it flags the init of the Application
    # to prevent building approval/clear programs until the precompile is
    # compiled so we have access to compiled information (its address for instance)
    verifier: Final[LSigPrecompile] = LSigPrecompile(EthEcdsaVerify(version=6))

    @external
    def check_eth_sig(
        self, hash: HashValue, signature: Signature, *, output: abi.String
    ):
        return Seq(
            # The precompiled lsig should have its address and binary available
            # here so we can use it to make sure we've been called
            # with the correct lsig
            Assert(Txn.sender() == self.verifier.logic.hash()),
            output.set("lsig validated"),
        )


def demo():
    algod_client = sandbox.get_algod_client()
    acct = sandbox.get_accounts().pop()

    # Create app client
    app_client = client.ApplicationClient(
        algod_client, EthChecker(), signer=acct.signer
    )

    # shouldn't have an approval program yet, since
    # the number of precompiles is > 0
    assert app_client.app.approval_program is None

    # This will first compile the precompiles, then compile the approval program
    # with the precompiles in place
    # not required to call manually since create/update will also do this
    # if necessary
    app_client.build()

    # Now we should have the approval program available
    assert app_client.app.approval_program is not None

    app_client.create()

    # Create a new app client with the lsig signer
    lsig_signer = cast(EthChecker, app_client.app).verifier.signer()
    lsig_client = app_client.prepare(signer=lsig_signer)

    atc = AtomicTransactionComposer()

    # Add a payment just to cover fees
    sp_with_fees = algod_client.suggested_params()
    sp_with_fees.flat_fee = True
    sp_with_fees.fee = consts.milli_algo * 3
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
    hex_signature = "5d99b6f7f6d1f73d1a26497f2b1c89b24c0993913f86e9a2d02cd69887d9c94f3c880358579d811b21dd1b7fd9bb01c1d81d10e69f0384e675c32b39643be8921b"
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        EthChecker.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    # V1
    hex_signature = "331fe75a821c982f9127538858900d87d3ec1f9f737338ad67cad133fa48feff48e6fa0c18abc62e42820f05943e47af3e9fbe306ce74d64094bdf1691ee53e01c"
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        EthChecker.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    result = atc.execute(algod_client, 4)
    for result in result.abi_results:
        print(result.return_value)


if __name__ == "__main__":
    demo()
