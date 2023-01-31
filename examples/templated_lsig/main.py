import base64
from copy import copy
from nacl.signing import SigningKey

from algosdk.encoding import decode_address
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)

from typing import Literal
from pyteal import Assert, Expr, abi, Txn, Ed25519Verify_Bare, Seq, Int, TealType
from beaker import sandbox, client, LogicSignatureTemplate, Application, consts
from beaker.precompile import LSigTemplatePrecompile

Signature = abi.StaticBytes[Literal[64]]


class App(Application):
    @staticmethod
    def SigChecker() -> LogicSignatureTemplate:
        # Simple program to check an ed25519 signature given a message and signature

        def evaluate(user_addr: Expr) -> Expr:
            return Seq(
                # Borrow the msg and sig from the abi call arguments
                # TODO: this kinda stinks, what do?
                (msg := abi.String()).decode(Txn.application_args[2]),
                (sig := abi.make(Signature)).decode(Txn.application_args[3]),
                # Assert that the sig matches
                Assert(Ed25519Verify_Bare(msg.get(), sig.get(), user_addr)),
                Int(1),
            )

        return LogicSignatureTemplate(
            evaluate,
            runtime_template_variables={"user_addr": TealType.bytes},
        )

    sig_checker: LSigTemplatePrecompile

    def __init__(self):
        super().__init__()

        @self.external
        def check(signer_address: abi.Address, msg: abi.String, sig: Signature):
            self.sig_checker = self.precompiled(self.SigChecker())
            return Assert(
                Txn.sender()
                == self.sig_checker.logic.template_address(
                    user_addr=signer_address.get()
                )
            )


def sign_msg(msg: str, sk: str) -> bytes:
    """utility function for signing arbitrary data"""
    pk = list(base64.b64decode(sk))
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
    with open("tmpl.teal", "w") as f:
        f.write(app.sig_checker.lsig.program)
    with open("tmp.teal.tok", "wb") as f:
        f.write(
            app.sig_checker.logic.populate_template(
                user_addr=decode_address(acct.address)
            )
        )

    # Get the signer for the lsig from its populated precompile
    lsig_signer = app.sig_checker.template_signer(
        user_addr=decode_address(acct.address)
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
        "check",
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
