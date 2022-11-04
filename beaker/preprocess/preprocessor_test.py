from pyteal import *
from .preprocessor import Preprocessor
from .builtins import *


def test_parse_method():
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


def test_built_ins():
    def meth():

        app_put("ok", 123)
        x = app_get("ok")
        app_del("ok")
        return x

    pp = Preprocessor(meth)
    print(pp.expr)
