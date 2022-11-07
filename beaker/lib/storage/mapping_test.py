import pyteal as pt
from .mapping import Mapping
from beaker.application import Application
from beaker.decorators import external

def test_mapping():

    class T(Application):
        m = Mapping(pt.abi.Address, pt.abi.Uint64)

        @external
        def thing(self, name: pt.abi.Address, *, output: pt.abi.Uint64):
            return self.m[name].store_into(output)

    t = T()
