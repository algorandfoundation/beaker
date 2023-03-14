from typing import Literal

import pyteal as pt

import beaker

Signature = pt.abi.StaticBytes[Literal[64]]


def lsig_validate(user_addr: pt.Expr) -> pt.Expr:
    """Simple program to check an ed25519 signature given a message and signature"""
    return pt.Seq(
        # Borrow the msg and sig from the app call arguments
        (msg := pt.abi.String()).decode(pt.Txn.application_args[2]),
        (sig := pt.abi.make(Signature)).decode(pt.Txn.application_args[3]),
        # Assert that the sig matches
        pt.Assert(pt.Ed25519Verify_Bare(msg.get(), sig.get(), user_addr)),
        pt.Int(1),
    )


lsig = beaker.LogicSignatureTemplate(
    lsig_validate,
    runtime_template_variables={"user_addr": pt.TealType.bytes},
)


app = beaker.Application("SigCheckerApp")


@app.external
def check(
    signer_address: pt.abi.Address, msg: pt.abi.String, sig: Signature
) -> pt.Expr:
    sig_checker_pc = beaker.precompiled(lsig)
    # The lsig will take care of verifying the signature
    # all we need to do is check that its been used to sign this transaction
    return pt.Assert(
        pt.Txn.sender() == sig_checker_pc.address(user_addr=signer_address.get())
    )
