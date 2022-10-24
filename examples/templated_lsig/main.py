import base64
from copy import copy
from nacl.signing import SigningKey

from algosdk.encoding import decode_address
from algosdk.future import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)

from typing import Literal
from pyteal import *
from beaker import *
from beaker.precompile import LSigPrecompile

Signature = abi.StaticBytes[Literal[64]]


class App(Application):
    class SigChecker(LogicSignature):
        # Simple program to check an ed25519 signature given a message and signature
        user_addr = TemplateVariable(stack_type=TealType.bytes)

        def evaluate(self):
            return Seq(
                # Borrow the msg and sig from the abi call arguments
                # TODO: this kinda stinks, what do?
                (msg := abi.String()).decode(Txn.application_args[2]),
                (sig := abi.make(Signature)).decode(Txn.application_args[3]),
                # Assert that the sig matches
                Assert(Ed25519Verify_Bare(msg.get(), sig.get(), self.user_addr)),
                Int(1),
            )

    sig_checker = LSigPrecompile(SigChecker())

    @external
    def check(self, signer_address: abi.Address, msg: abi.String, sig: Signature):
        return Assert(
            Txn.sender() == self.sig_checker.logic.template_hash(signer_address.get())
        )


def sign_msg(msg: str, sk: str) -> bytes:
    """utility function for signing arbitrary data"""
    pk: list[bytes] = list(base64.b64decode(sk))
    return SigningKey(bytes(pk[:32])).sign(msg.encode()).signature


def demo():
    acct = sandbox.get_accounts().pop()

    # Create app client
    app = App()
    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), app, signer=acct.signer
    )

    # deploy app
    app_client.create()

    # Write the populated template as binary
    # with open("tmp.teal.tok", "wb") as f:
    #     f.write(app.sig_checker.populate_template(decode_address(acct.address)))

    # Get the signer for the lsig from its populated precompile
    lsig_signer = app.sig_checker.template_signer(decode_address(acct.address))
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
        App.check,
        suggested_params=free_sp,
        signer_address=acct.address,
        msg=msg,
        sig=sig,
    )

    # run it
    result = atc.execute(app_client.client, 4)
    print(f"Confirmed in round {result.confirmed_round}")


if __name__ == "__main__":
    demo()
