import pytest
import pyteal as pt
from beaker.logic_signature import LogicSignature
from beaker.precompile import Precompile
from beaker.application import Application
from beaker.decorators import external
from beaker.client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client


def test_precompile():
    class Lsig(LogicSignature):
        def evaluate(self):
            return pt.Seq(pt.Assert(pt.Int(1)), pt.Int(1))

    class App(Application):
        pc = Precompile(Lsig)

        @external
        def check_it(self):
            return pt.Assert(pt.Txn.sender() == self.pc.address())

    app = App()
    ac = ApplicationClient(get_algod_client(), app, signer=get_accounts().pop().signer)
    print(ac.create())
