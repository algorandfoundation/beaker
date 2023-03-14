from typing import Literal

from pyteal import Assert, Ed25519Verify_Bare, Expr, Int, Seq, TealType, Txn, abi

from beaker import (
    Application,
    LogicSignatureTemplate,
    precompiled,
)

Signature = abi.StaticBytes[Literal[64]]


def SigChecker() -> LogicSignatureTemplate:  # noqa: N802
    # Simple program to check an ed25519 signature given a message and signature

    def evaluate(user_addr: Expr) -> Expr:
        return Seq(
            # Borrow the msg and sig from the app call arguments
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


sig_checker = SigChecker()

app = Application("SigCheckerApp")


@app.external
def check(signer_address: abi.Address, msg: abi.String, sig: Signature) -> Expr:
    sig_checker_pc = precompiled(sig_checker)
    # The lsig will take care of verifying the signature
    # all we need to do is check that its been used to sign this transaction
    return Assert(
        Txn.sender() == sig_checker_pc.address(user_addr=signer_address.get())
    )
