from pyteal import *
from beaker import *


class KeySig(LogicSignature):
    def evaluate(self):
        return Seq(
            Pop(Tmpl.Bytes("TMPL_NONCE")),
            Approve(),
        )
