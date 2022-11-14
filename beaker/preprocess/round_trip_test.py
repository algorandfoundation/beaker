import ast
import pyteal as pt
from .unprocessor import Unprocessor
from .preprocessor import Preprocessor


def test_round_trip():
    def meth():
        x = 1
        x += 2
        return x

    pp = Preprocessor(meth)
    expr = pp.expr()

    up = Unprocessor(expr)
    actual = ast.unparse(up.native_ast)
    expected = pp.src
    print(actual)
    print(expected)
