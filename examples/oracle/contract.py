from pyteal import *
from beaker.contracts.arcs import ARC21


class Oracle(ARC21):
    pass


if __name__ == "__main__":
    o = Oracle()
    print(o.contract.dictify())
