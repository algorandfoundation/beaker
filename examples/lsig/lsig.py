from typing import Literal
from pyteal import *
from beaker import *


HashValue = abi.StaticArray[abi.Byte, Literal[32]]
Signature = abi.StaticArray[abi.Byte, Literal[65]]


class EthEcdsaVerify(LogicSignature):
    """
    This Lsig has a single method called `validate` that takes two application arguments:
      hash, signature
    and returns the validity of the hash given the signature
    as written in OpenZeppelin https://docs.openzeppelin.com/contracts/2.x/api/cryptography#ECDSA-recover-bytes32-bytes-
    (65-byte signatures only)
    """

    def evaluate(self):
        return Seq(
            Assert(Txn.type_enum() == TxnType.ApplicationCall),
            self.eth_ecdsa_validate(Txn.application_args[1], Txn.application_args[2]),
        )

    @internal(TealType.uint64)
    def eth_ecdsa_validate(self, hash_value: Expr, signature: Expr) -> Expr:
        """
        Equivalent of OpenZeppelin ECDSA.recover for long 65-byte Ethereum signatures
        https://docs.openzeppelin.com/contracts/2.x/api/cryptography#ECDSA-recover-bytes32-bytes-
        Short 64-byte Ethereum signatures require some changes to the code

        Return a 20-byte Ethereum address

        Note: Unless compatibility with Ethereum or another system is necessary,
        we highly recommend using ed25519_verify instead of ecdsa on Algorand

        WARNING: This code has NOT been audited
        DO NOT USE IN PRODUCTION
        """

        r = Extract(signature, Int(0), Int(32))
        s = Extract(signature, Int(32), Int(32))

        # The recovery ID is shifted by 27 on Ethereum
        # For non-Ethereum signatures, remove the -27 on the line below
        v = Btoi(Extract(signature, Int(64), Int(1))) - Int(27)

        return Seq(
            Assert(
                Len(signature) == Int(65),
                Len(hash_value) == Int(32),
                # The following two asserts are to prevent malleability like in
                # https://github.com/OpenZeppelin/openzeppelin-contracts/blob/
                # 5fbf494511fd522b931f7f92e2df87d671ea8b0b/contracts/utils/cryptography/ECDSA.sol#L153
                BytesLe(
                    s,
                    Bytes(
                        "base16",
                        "0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0",
                    ),
                ),
                v <= Int(1),
            ),
            EcdsaVerify(
                EcdsaCurve.Secp256k1,
                hash_value,
                r,
                s,
                EcdsaRecover(EcdsaCurve.Secp256k1, hash_value, v, r, s),
            ),
        )
