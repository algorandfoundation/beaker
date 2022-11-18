import ast
from .unprocessor import Unprocessor
from .preprocessor import Preprocessor


def test_round_trip_method():
    def meth():
        var_256 = 1
        var_256 = var_256 + 2
        return var_256

    pp = Preprocessor(meth)
    up = Unprocessor(
        pp.function_body(), name=pp.fn_name, args=pp.args, returns=pp.return_type
    )
    actual = ast.unparse(up.native_ast)

    assert actual.strip() == pp.src.strip()
