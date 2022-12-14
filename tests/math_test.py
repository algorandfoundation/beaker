import math as pymath

import pyteal as pt
import beaker as bkr

from beaker.testing.unit_testing_helpers import UnitTestingApp, assert_output

import beaker.lib.math as math


def test_even():
    class EvenTester(UnitTestingApp):
        @bkr.external
        def unit_test(self, num: pt.abi.Uint64, *, output: pt.abi.Bool):
            return output.set(math.even(num.get()))

    num = 5
    inputs = [num, num - 1]
    output = [x % 2 == 0 for x in inputs]
    assert_output(EvenTester(), [{"num": n} for n in inputs], output)


def test_odd():
    class OddTester(UnitTestingApp):
        @bkr.external
        def unit_test(self, num: pt.abi.Uint64, *, output: pt.abi.Bool):
            return output.set(math.odd(num.get()))

    num = 5
    inputs = [num, num - 1]
    output = [x % 2 != 0 for x in inputs]

    assert_output(OddTester(), [{"num": n} for n in inputs], output)


def test_pow10():
    class Pow10Tester(UnitTestingApp):
        @bkr.external
        def unit_test(self, num: pt.abi.Uint64, *, output: pt.abi.Uint64):
            return output.set(math.pow10(num.get()))

    num = 3
    inputs = [num]
    output = [int(10**x) for x in inputs]

    assert_output(Pow10Tester(), [{"num": n} for n in inputs], output)


def test_min():
    class MinTester(UnitTestingApp):
        @bkr.external
        def unit_test(
            self, a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
        ):
            return output.set(math.min(a.get(), b.get()))

    inputs = [(100, 10)]
    output = [min(a, b) for a, b in inputs]

    assert_output(MinTester(), [{"a": a, "b": b} for a, b in inputs], output)


def test_max():
    class MaxTester(UnitTestingApp):
        @bkr.external
        def unit_test(
            self, a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
        ):
            return output.set(math.max(a.get(), b.get()))

    inputs = [(100, 10)]
    output = [max(a, b) for a, b in inputs]

    assert_output(MaxTester(), [{"a": a, "b": b} for a, b in inputs], output)


def test_div_ceil():
    class DivCeilTester(UnitTestingApp):
        @bkr.external
        def unit_test(
            self, a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64
        ):
            return output.set(math.div_ceil(a.get(), b.get()))

    inputs = [(100, 3)]
    output = [pymath.ceil(a / b) for a, b in inputs]

    assert_output(DivCeilTester(), [{"a": a, "b": b} for a, b in inputs], output)


def test_saturate():
    class DivCeilTester(UnitTestingApp):
        @bkr.external
        def unit_test(
            self,
            a: pt.abi.Uint64,
            b: pt.abi.Uint64,
            c: pt.abi.Uint64,
            *,
            output: pt.abi.Uint64
        ):
            return output.set(math.saturate(a.get(), b.get(), c.get()))

    inputs = [(50, 100, 20), (15, 100, 20), (150, 100, 20)]
    output = [max(min(b, a), c) for a, b, c in inputs]

    assert_output(
        DivCeilTester(), [{"a": a, "b": b, "c": c} for a, b, c in inputs], output
    )


def test_wide_factorial():
    class WideFactorialTester(UnitTestingApp):
        @bkr.external
        def unit_test(self, num: pt.abi.Uint64, *, output: pt.abi.Uint64):
            return output.set(pt.Btoi(math.wide_factorial(num.encode())))

    num = 5
    inputs = [num]
    output = [pymath.factorial(num) for num in inputs]
    assert_output(WideFactorialTester(), [{"num": num} for num in inputs], output)


def test_exponential():
    class WideFactorialTester(UnitTestingApp):
        @bkr.external
        def unit_test(
            self, num: pt.abi.Uint64, iters: pt.abi.Uint64, *, output: pt.abi.Uint64
        ):
            return output.set(math.exponential(num.get(), iters.get()))

    num = 10
    iters = 30
    inputs = [(num, iters)]
    output = [int(pymath.exp(num)) for num, _ in inputs]

    assert_output(
        WideFactorialTester(),
        [{"num": num, "iters": iters} for num, iters in inputs],
        output,
        opups=15,
    )


# def test_ln():
#   num = 10
#   expr = Log(Itob(ln(Int(num))))
#   output = [logged_int(int(pymath.log(num)))]
#   assert_output(expr, output, pad_budget=15)

# def test_log2():
#   num = 17
#   expr = Log(Itob(log2(Int(num))))
#   output = [logged_int(int(pymath.log2(num)))]
#   assert_output(expr, output, pad_budget=15)

# def test_log10():
#    num = 123123123
#    expr = Log(Itob(scaled_log10(Int(num))))
#    output = [logged_int(int(pymath.log10(num)))]
#    assert_output(expr, output)

# def test_negative_power():
#    expr = Log(negative_power(Int(100), Int(3)))
#    output = [logged_int(int(math.pow(100, -3)))]
#    assert_output(expr, output)
