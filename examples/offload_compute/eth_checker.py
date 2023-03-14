from typing import Literal

import pyteal as pt

import beaker


@pt.Subroutine(pt.TealType.uint64)
def eth_ecdsa_validate(hash_value: pt.Expr, signature: pt.Expr) -> pt.Expr:
    """
    Return a 1/0 for valid signature given hash

    Equivalent of OpenZeppelin ECDSA.recover for long 65-byte Ethereum signatures
    https://docs.openzeppelin.com/contracts/2.x/api/cryptography#ECDSA-recover-bytes32-bytes-
    Short 64-byte Ethereum signatures require some changes to the code


    [1] https://github.com/OpenZeppelin/openzeppelin-contracts/blob/5fbf494511fd522b931f7f92e2df87d671ea8b0b/contracts/utils/cryptography/ECDSA.sol#L153


    Note: Unless compatibility with Ethereum or another system is necessary,
    we highly recommend using ed25519_verify instead of ecdsa on Algorand

    WARNING: This code has NOT been audited
    DO NOT USE IN PRODUCTION
    """

    r = pt.Extract(signature, pt.Int(0), pt.Int(32))
    s = pt.Extract(signature, pt.Int(32), pt.Int(32))

    # The recovery ID is shifted by 27 on Ethereum
    # For non-Ethereum signatures, remove the -27 on the line below
    v = pt.Btoi(pt.Extract(signature, pt.Int(64), pt.Int(1))) - pt.Int(27)

    return pt.Seq(
        pt.Assert(
            pt.Len(signature) == pt.Int(65),
            pt.Len(hash_value) == pt.Int(32),
            # The following two asserts are to prevent malleability like in [1]
            pt.BytesLe(
                s,
                pt.Bytes(
                    "base16",
                    "0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0",
                ),
            ),
            v <= pt.Int(1),
        ),
        pt.EcdsaVerify(
            pt.EcdsaCurve.Secp256k1,
            hash_value,
            r,
            s,
            pt.EcdsaRecover(pt.EcdsaCurve.Secp256k1, hash_value, v, r, s),
        ),
    )


verify_lsig = beaker.LogicSignature(
    pt.Seq(
        pt.Assert(
            # Don't let it be rekeyed
            pt.Txn.rekey_to() == pt.Global.zero_address(),
            # Don't take a fee from me
            pt.Txn.fee() == pt.Int(0),
            # Make sure I've signed an app call
            pt.Txn.type_enum() == pt.TxnType.ApplicationCall,
            # Make sure I have the args I expect [method_selector, hash_value, signature]
            pt.Txn.application_args.length() == pt.Int(3),
        ),
        eth_ecdsa_validate(pt.Txn.application_args[1], pt.Txn.application_args[2]),
    ),
    build_options=beaker.BuildOptions(avm_version=6),
)
"""
This LogicSignature takes two application arguments:
  hash, signature
and returns the validity of the signature given the hash
as written in OpenZeppelin https://docs.openzeppelin.com/contracts/2.x/api/cryptography#ECDSA-recover-bytes32-bytes-
(65-byte signatures only)
"""

app = beaker.Application("EthChecker")


@app.external
def check_eth_sig(
    hash: pt.abi.StaticBytes[Literal[32]],
    signature: pt.abi.StaticBytes[Literal[65]],
    *,
    output: pt.abi.String
) -> pt.Expr:
    # The lsig that will be responsible for validating the
    # incoming signature against the incoming hash
    # When passed to Precompile, it flags the init of the Application
    # to prevent building approval/clear programs until the precompile is
    # compiled so we have access to compiled information (its address for instance)
    verifier = beaker.precompiled(verify_lsig)

    return pt.Seq(
        # The precompiled lsig should have its address and binary available
        # here so we can use it to make sure we've been called
        # with the correct lsig
        pt.Assert(pt.Txn.sender() == verifier.address()),
        output.set("lsig validated"),
    )
