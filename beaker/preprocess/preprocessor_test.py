import pyteal as pt
from beaker.application import Application
from beaker.decorators import external

from .preprocessor import Preprocessor
from ._builtins import app_get, app_put, app_del, concat, u64

TODOS = """
    List:
        Create
        Append
        Pop

    Tuple:
        Create
        Element wise access

    allow + to map to concat for string types

"""


def compile(e: pt.Expr) -> str:
    return pt.compileTeal(
        e,
        mode=pt.Mode.Application,
        version=8,
        optimize=pt.OptimizeOptions(scratch_slots=True),
    )


def test_parse_method():
    def meth():
        x = 3
        y = 2**2

        # Augmented assignment (load,op,store)
        x += 3
        x *= 3

        # Both mapped to truncated division
        x /= 3
        x //= 3

        z = "ok"

        while y > 0:
            y -= 1

        # `range` is a "builtin" we provide
        for _ in range(3):
            # TODO: map to concat if the type is a string
            z += "no way"

        if x * y:
            return 1

        return x

    Preprocessor(meth).expr()


def test_if_else():
    def meth():
        x = 3

        # if
        if x > 10:
            return 10

        # if else
        if x < 10:
            return 10
        else:
            x = 10

        # if elseif
        if x > 10:
            return 10
        elif x < 10:
            return 5

        # if elseif else
        if x > 2:
            return 1
        elif x > 3:
            return 2
        else:
            return 3

    Preprocessor(meth).expr()


def test_bool_op():
    def meth():
        x = 1
        y = 2
        z = False
        z = 1 and 2
        z = (x and y and x) or y
        z = not (x or y)
        return z

    Preprocessor(meth).expr()


def test_int_ops():
    def meth():
        # int math
        x = 3 - 3
        x = 3 / 3
        x = 3 // 3
        x = 3 * 3
        x = 3**3
        x = 3 % 3

        # compare
        x = 3 == 3
        x = 3 != 3
        x = 3 < 3
        x = 3 <= 3
        x = 3 > 3
        x = 3 >= 3

        # bitwise
        x = 3 | 1
        x = 3 ^ 1
        x = 3 & 1
        x = 3 >> 1
        x = 3 << 1
        x = x

    Preprocessor(meth).expr()


def test_bytes_ops():
    def meth():
        # byteint math
        val = b"deadbeef"
        x = val - val
        x = val / val
        x = val // val
        x = val * val
        x = val % val

        # compare
        y = val == val
        y = val != val
        y = val < val
        y = val <= val
        y = val > val
        y = val >= val
        y = y and y

        # bitwise
        x = x | val
        x = val ^ val
        x = val & val

        # Unsupported
        # x = val ** val
        # x = val >> val
        # x = val << val

    Preprocessor(meth).expr()


def test_str_ops():
    def meth():
        s = "stringy"
        return len(concat(s, "hi"))

    expr = Preprocessor(meth).expr()
    print(compile(expr))


# def test_list_ops():
#    def meth():
#        z = [1, 2, 3]
#        z
#
#    expr = Preprocessor(meth).expr()
#    print(expr)
#    # print(compile(expr))


def test_built_ins():
    # TODO: all the others
    def meth():
        app_put("ok", 123)
        x = app_get("ok")
        app_del("ok")
        return x

    print(compile(Preprocessor(meth).expr()))


def test_arg_returns():
    class ArgReturn(Application):
        @external(translate=True)
        def no_args_no_output(self):
            x = 2
            x += 3
            assert 0, "bad"

        @external(translate=True)
        def no_args_yes_output_py(self) -> int:
            return 2

        @external(translate=True)
        def yes_args_no_output_py(self, x: int):
            x += 1

        @external(translate=True)
        def yes_args_yes_output_py(self, x: int) -> int:
            return x

    ar = ArgReturn()
    assert len(ar.approval_program) > 0


def test_kitchen_sink():
    class KitchenSink(Application):
        @external(translate=True)
        def add(self, x: int, y: int) -> int:
            sum = x + y
            return sum

        @external(translate=True)
        def add_sequence(self, x: u64) -> u64:
            sum = 1
            for y in range(x):
                sum += y
            return sum

        @external(translate=True)
        def sum(self, arr: list[u64]) -> u64:
            sum = 0
            for x in arr:
                sum += x
            return sum

        @external(translate=True)
        def echo(self, msg: str) -> str:
            return msg

    ks = KitchenSink()
    print(ks.approval_program)


def test_calculator_app():
    class Calculator(Application):
        @external(translate=True)
        def add(self, x: u64, y: u64) -> u64:
            return x + y

        @external(translate=True)
        def sub(self, x: u64, y: u64) -> u64:
            return x - y

        @external(translate=True)
        def mul(self, x: u64, y: u64) -> u64:
            return x * y

        @external(translate=True)
        def div(self, x: u64, y: u64) -> u64:
            return x / y

    calc = Calculator()
    print(calc.approval_program)
