from pyteal import *
from beaker.application import Application
from beaker.decorators import external

from .preprocessor import Preprocessor
from .builtins import *


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
            # maps to concat if the type is a string
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

        ## compare
        y = val == val
        y = val != val
        y = val < val
        y = val <= val
        y = val > val
        y = val >= val

        ## bitwise
        x = val | val
        x = val ^ val
        x = val & val

        # Unsupported
        # x = val ** val
        # x = val >> val
        # x = val << val

    Preprocessor(meth).expr()


def test_built_ins():
    # TODO: all the others
    def meth():
        app_put("ok", 123)
        x = app_get("ok")
        app_del("ok")
        return x

    Preprocessor(meth).expr()


def test_app():
    class App(Application):
        @external(translate=True)
        def no_args_no_output(self):
            x = 2
            x += 3
            assert 0, "bad"

        @external
        def no_args_yes_output_pt(self, *, output: abi.Uint64) -> Expr:
            return output.set(Int(2))

        @external(translate=True)
        def no_args_yes_output_py(self) -> int:
            return 2

        @external(translate=True)
        def yes_args_no_output_py(self, x: int) -> int:
            return x

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

    app = App()
    # print(app.approval_program)
