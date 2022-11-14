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
    expected = pp.src

    up = Unprocessor(pp.expr(), name=pp.fn_name, args=pp.args, returns=pp.return_type)
    actual = ast.unparse(up.native_ast)
    print()
    print(actual)
    print()
    print(expected)
