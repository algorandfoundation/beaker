from typing import Final
from beaker import *
from pyteal import *

if __name__ == "__main__":
    from lsig import EthEcdsaVerify, HashValue, Signature
else:
    from .lsig import EthEcdsaVerify, HashValue, Signature


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
