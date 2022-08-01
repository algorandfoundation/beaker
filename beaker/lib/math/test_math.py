import math as pymath
from pyteal import Int, Itob, Log, Seq

from tests.helpers import assert_output, logged_int

from .math import (
    div_ceil,
    even,
    max,
    odd,
    pow10,
    saturate,
    wide_factorial,
    bytes_to_int,
    exponential,
)


def test_even():
    num = 5
    expr = Seq(Log(Itob(even(Int(num)))), Log(Itob(even(Int(num - 1)))))
    output = [logged_int(0), logged_int(1)]
    assert_output(expr, output, pad_budget=15)


def test_odd():
    num = 6
    expr = Seq(Log(Itob(odd(Int(num)))), Log(Itob(odd(Int(num - 1)))))
    output = [logged_int(0), logged_int(1)]
    assert_output(expr, output, pad_budget=15)


def test_pow10():
    expr = Log(Itob(pow10(Int(3))))
    output = [logged_int(int(1e3))]
    assert_output(expr, output)


def test_min():
    expr = Log(Itob(min(Int(100), Int(10))))
    output = [logged_int(int(10))]
    assert_output(expr, output)


def test_max():
    expr = Log(Itob(max(Int(100), Int(10))))
    output = [logged_int(int(100))]
    assert_output(expr, output)


def test_div_ceil():
    expr = Log(Itob(div_ceil(Int(100), Int(3))))
    output = [logged_int(int(34))]
    assert_output(expr, output)


def test_saturate():
    expr = Log(Itob(saturate(Int(50), Int(100), Int(20))))
    output = [logged_int(int(50))]
    assert_output(expr, output)

    expr = Log(Itob(saturate(Int(15), Int(100), Int(20))))
    output = [logged_int(int(20))]
    assert_output(expr, output)

    expr = Log(Itob(saturate(Int(150), Int(100), Int(20))))
    output = [logged_int(int(100))]
    assert_output(expr, output)


def test_wide_factorial():
    num = 5
    expr = Log(Itob(bytes_to_int(wide_factorial(Itob(Int(num))))))
    output = [logged_int(int(pymath.factorial(num)))]
    assert_output(expr, output, pad_budget=15)


def test_exponential():
    num = 10
    expr = Log(Itob(exponential(Int(num), Int(30))))
    output = [logged_int(int(pymath.exp(num)))]
    assert_output(expr, output, pad_budget=15)


# def test_ln():
#   num = 10
#   expr = Log(Itob(ln(Int(num))))
#   output = [logged_int(int(pymath.log(num)))]
#   assert_output(expr, output, pad_budget=15)


# def test_log2():
#   num = 17
#   expr = Log(Itob(log2(Int(num))))
#   output = [logged_int(int(pymath.log2(num)))]
#   print(pymath.log2(num))
#   assert_output(expr, output, pad_budget=15)


# def test_log10():
#    num = 123123123
#    expr = Log(Itob(scaled_log10(Int(num))))
#    output = [logged_int(int(pymath.log10(num)))]
#    print(pymath.log10(num))
#    assert_output(expr, output)

# def test_negative_power():
#    expr = Log(negative_power(Int(100), Int(3)))
#    output = [logged_int(int(math.pow(100, -3)))]
#    assert_output(expr, output)
