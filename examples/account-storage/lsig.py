from pyteal import *
from beaker import *


class KeySig(LogicSignature):
    def evaluate(self):
        return Seq(
            Pop(Tmpl.Bytes("TMPL_NONCE")),
            Pop(Tmpl.Int("TMPL_INTY")),
            Pop(Tmpl.Bytes("TMPL_NONCER")),
            Pop(Tmpl.Int("TMPL_INTEROO")),
            Approve(),
        )
