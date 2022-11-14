import ast
import pyteal as pt
from .unprocessor import Unprocessor
from .preprocessor import Preprocessor


def test_round_trip():
    def meth():
        var_256 = 1
        var_256 = var_256 + 2
        return var_256

    pp = Preprocessor(meth)
    up = Unprocessor(pp.expr())

    print()
    print(ast.unparse(up.native_ast))
    print()
    print(pp.src)
