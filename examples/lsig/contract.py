from typing import Final
from beaker import *
from beaker.lib.strings import encode_uvarint
from pyteal import *
from lsig import EthEcdsaVerify, HashValue, Signature


class Precompile:
    def __init__(self, lsig_type: type[LogicSignature]):
        self.lsig_type = lsig_type

    def address(self) -> Expr:
        pass

    # def template_address(key: TealType.bytes):
    #    return Sha512_256(
    #        Concat(
    #            Bytes(consts.PROGRAM_DOMAIN_SEPARATOR),
    #            Extract(
    #                sig_bytes, Int(0), key_idx
    #            ),  # Take the bytes up to where the key should be
    #            encode_uvarint(
    #                Len(key), Bytes("")
    #            ),  # The length of the bytestring is encoded as uvarint
    #            key,
    #            Suffix(
    #                sig_bytes, Len(sig_bytes) - key_idx - Int(1)
    #            ),  # append the bytes from the key onward
    #        )
    #    )


class EthChecker(Application):

    # The lsig that will be responsible for validating the
    # incoming signature against the incoming hash
    verifier: Final[Precompile] = Precompile(EthEcdsaVerify)

    @external
    def check_eth_sig(
        self, hash: HashValue, signature: Signature, *, output: abi.String
    ):
        return Seq(
            Assert(Txn.sender() == self.verifier.address()),
            output.set("lsig validated"),
        )
