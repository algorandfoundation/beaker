import pyteal as pt
import inspect

from beaker.application import Application
from beaker.decorators import external, internal
from beaker.client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client

from beaker.testing import UnitTestingApp, assert_output, returned_int_as_bytes

from .preprocessor import Preprocessor
from ._builtins import app_get, app_put, app_del, concat, u64, log, i, bigint, string


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

    compile(Preprocessor(meth).function_body())


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

    compile(Preprocessor(meth).function_body())


def test_bool_op():
    def meth():
        x = 1
        y = 2
        z = False
        z = 1 and 2
        z = (x and y and x) or y
        z = not (x or y)
        return z

    compile(Preprocessor(meth).function_body())


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
        return x

    compile(Preprocessor(meth).function_body())


def test_bytes_ops():
    def meth():
        # byteint math
        val: bigint = b"deadbeef"
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
        return len(x)

    teal = compile(Preprocessor(meth).function_body())
    assert len(teal) > 0


def test_str_ops():
    def meth():
        s: str = "stringy"
        return len(concat(s, "hi"))

    compile(Preprocessor(meth).function_body())


def test_built_ins():
    # TODO: all the others
    def meth():
        app_put("ok", 123)
        x = app_get("ok")
        app_del("ok")
        return x

    compile(Preprocessor(meth).function_body())


def test_arg_returns():
    class ArgReturn(Application):
        @external(translate=True)
        def no_args_no_output(self):
            x = 2
            x += 3
            assert 0, "bad"

        @external(translate=True)
        def no_args_yes_output_py(self) -> u64:
            return 2

        @external(translate=True)
        def yes_args_no_output_py(self, x: u64):
            x += 1

        @external(translate=True)
        def yes_args_yes_output_py(self, x: u64) -> u64:
            return x

    ar = ArgReturn()
    assert len(ar.approval_program) > 0


def test_kitchen_sink():
    class KitchenSink(Application):
        @external(translate=True)
        def add(self, x: u64, y: u64) -> u64:
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
        def echo(self, msg: string) -> string:
            return msg

    ks = KitchenSink()
    assert len(ks.approval_program) > 0


class NativeApplication(Application):
    def __init__(self, version=pt.MAX_TEAL_VERSION):

        self._user_defined = {
            ud: (getattr(self, ud), inspect.getattr_static(self, ud))
            for ud in list(set(dir(self)) - set(dir(Application)))
        }

        # TODO: we're overriding the methods defined on the class during init.
        # If you try to initialized >1 time, it breaks stuff. Fix that.
        for name, (_, static_attr) in self._user_defined.items():
            pp = Preprocessor(static_attr, self)
            # Treat underscore prefixed methods as internal
            setattr(
                self.__class__,
                name,
                internal(pp.return_stack_type)(pp.subroutine())
                if name.startswith("_")
                else external(pp.subroutine()),
            )

        super().__init__(version=version)


def test_calculator_app():
    class Calculator(NativeApplication):
        def add(self, x: u64, y: u64) -> u64:
            return x + y

        def sub(self, x: u64, y: u64) -> u64:
            return x - y

        def mul(self, x: u64, y: u64) -> u64:
            return x * y

        def div(self, x: u64, y: u64) -> u64:
            return x / y

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), Calculator(), signer=acct.signer)
    ac.create()

    result = ac.call(Calculator.add, x=2, y=2)
    assert result.return_value == 4

    result = ac.call(Calculator.sub, x=6, y=1)
    assert result.return_value == 5

    result = ac.call(Calculator.mul, x=6, y=3)
    assert result.return_value == 18

    result = ac.call(Calculator.div, x=25, y=5)
    assert result.return_value == 5


def test_native_app():
    class Native(NativeApplication):
        def ok(self):
            log("ok")

        def ok_caller(self):
            self.ok()

        def sqr(self, a: u64) -> u64:
            return self._sqr(a)

        def _sqr(self, a: u64) -> i:
            return a**2

    acct = get_accounts().pop()
    ac = ApplicationClient(get_algod_client(), Native(), signer=acct.signer)
    ac.create()

    result = ac.call(Native.sqr, a=2)
    assert result.return_value == 4


def test_recursive_func():
    # Define recursive function using python syntax
    def factorial(x: i) -> i:
        return x * factorial(x - 1) if x > 0 else 1

    val = 10
    # Call the logic in Python :brain-explode:
    expected = factorial(val)

    # Translate the python logic to PyTeal AST
    pp = Preprocessor(factorial)

    # Get the expression resulting from a SubroutineCall to our translated
    # function
    expr = pp.callable(pt.Int(val))

    # Deploy an app on chain to run the logic in the AVM
    ut = UnitTestingApp(pt.Itob(expr))
    output = [returned_int_as_bytes(expected)]
    assert_output(ut, [], output)

    print(f"\n{compile(expr)}")
