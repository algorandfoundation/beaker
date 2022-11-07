import pyteal as pt
from .mapping import Mapping

def test_mapping():
    m = Mapping(pt.abi.Address, pt.abi.Uint64)

