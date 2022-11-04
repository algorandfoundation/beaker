from pyteal import *
from .preprocessor import Preprocessor


def test_parse_exprs():
    def meth():
        x = 3
        y = 2**2
        x += 3
        x *= 3
        x /= 3

        x //= 3

        z = "ok"

        while y > 0:
            y -= 1

        for _ in range(3):
            z += "no way"

        if x * y:
            return 1

        return x

    pp = Preprocessor(meth)
    print(pp.expr)
    print(compileTeal(pp.expr, mode=Mode.Application, version=8))
