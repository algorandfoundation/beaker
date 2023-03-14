import math as pymath

import pyteal as pt

from beaker.lib import math

from tests.helpers import UnitTestingApp, assert_output


def test_even() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(num: pt.abi.Uint64, *, output: pt.abi.Bool) -> pt.Expr:
        return output.set(math.Even(num.get()))

    num = 5
    inputs = [num, num - 1]
    output = [x % 2 == 0 for x in inputs]
    assert_output(app, [{"num": n} for n in inputs], output)


def test_odd() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(num: pt.abi.Uint64, *, output: pt.abi.Bool) -> pt.Expr:
        return output.set(math.Odd(num.get()))

    num = 5
    inputs = [num, num - 1]
    output = [x % 2 != 0 for x in inputs]

    assert_output(app, [{"num": n} for n in inputs], output)


def test_pow10() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(num: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(math.Pow10(num.get()))

    num = 3
    inputs = [num]
    output = [int(10**x) for x in inputs]

    assert_output(app, [{"num": n} for n in inputs], output)


def test_min() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(
        a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        return output.set(math.Min(a.get(), b.get()))

    inputs = [(100, 10)]
    output = [min(a, b) for a, b in inputs]

    assert_output(app, [{"a": a, "b": b} for a, b in inputs], output)


def test_max() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(
        a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        return output.set(math.Max(a.get(), b.get()))

    inputs = [(100, 10)]
    output = [max(a, b) for a, b in inputs]

    assert_output(app, [{"a": a, "b": b} for a, b in inputs], output)


def test_div_ceil() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(
        a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        return output.set(math.DivCeil(a.get(), b.get()))

    inputs = [(100, 3)]
    output = [pymath.ceil(a / b) for a, b in inputs]

    assert_output(app, [{"a": a, "b": b} for a, b in inputs], output)


def test_saturate() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(
        a: pt.abi.Uint64, b: pt.abi.Uint64, c: pt.abi.Uint64, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        return output.set(math.Saturate(a.get(), b.get(), c.get()))

    inputs = [(50, 100, 20), (15, 100, 20), (150, 100, 20)]
    output = [max(min(b, a), c) for a, b, c in inputs]

    assert_output(app, [{"a": a, "b": b, "c": c} for a, b, c in inputs], output)


def test_wide_factorial() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(num: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(pt.Btoi(math.WideFactorial(num.encode())))

    num = 5
    inputs = [num]
    output = [pymath.factorial(num) for num in inputs]
    assert_output(app, [{"num": num} for num in inputs], output)


def test_exponential() -> None:
    app = UnitTestingApp()

    @app.external
    def unit_test(
        num: pt.abi.Uint64, iters: pt.abi.Uint64, *, output: pt.abi.Uint64
    ) -> pt.Expr:
        return output.set(math.Exponential(num.get(), iters.get()))

    num = 10
    iters = 30
    inputs = [(num, iters)]
    output = [int(pymath.exp(num)) for num, _ in inputs]

    assert_output(
        app,
        [{"num": num, "iters": iters} for num, iters in inputs],
        output,
        opups=15,
    )


# def test_ln() -> None:
#   num = 10
#   expr = Log(Itob(ln(Int(num))))
#   output = [logged_int(int(pymath.log(num)))]
#   assert_output(expr, output, pad_budget=15)

# def test_log2() -> None:
#   num = 17
#   expr = Log(Itob(log2(Int(num))))
#   output = [logged_int(int(pymath.log2(num)))]
#   assert_output(expr, output, pad_budget=15)

# def test_log10() -> None:
#    num = 123123123
#    expr = Log(Itob(scaled_log10(Int(num))))
#    output = [logged_int(int(pymath.log10(num)))]
#    assert_output(expr, output)

# def test_negative_power() -> None:
#    expr = Log(negative_power(Int(100), Int(3)))
#    output = [logged_int(int(math.pow(100, -3)))]
#    assert_output(expr, output)
