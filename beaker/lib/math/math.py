import math

from pyteal import (
    BitLen,
    BytesAdd,
    BytesDiv,
    BytesMinus,
    BytesMul,
    Btoi,
    Concat,
    Exp,
    Expr,
    ExtractUint64,
    If,
    Int,
    Itob,
    Len,
    Not,
    Return,
    ScratchSlot,
    Seq,
    Subroutine,
    TealType,
)

from beaker.lib.inline import InlineAssembly

_scale = 1000000
_log2_10 = math.log2(10)
_log2_e = math.log2(math.e)

_max_uint = (2**64) - 1
_half_uint = (2**32) - 1

log2_10 = Int(int(_log2_10 * _scale))
log2_e = Int(int(_log2_e * _scale))
scale = Int(_scale)

max_uint = Int(_max_uint)
half_uint = Int(_half_uint)


@Subroutine(TealType.uint64)
def odd(x):
    """odd returns 1 if x is odd

    Args:
        x: uint64 to evaluate

    Returns:
        uint64 1 or 0 where 1 is true and 0 is false

    """
    return x & Int(1)


@Subroutine(TealType.uint64)
def even(x):
    """even returns 1 if x is even

    Args:
        x: uint64 to evaluate

    Returns:
        uint64 1 or 0 where 1 is true and 0 is false


    """
    return Not(odd(x))


@Subroutine(TealType.uint64)
def max(a, b) -> Expr:
    """max returns the max of 2 integers"""
    return If(a > b, a, b)


@Subroutine(TealType.uint64)
def min(a, b) -> Expr:
    """min returns the min of 2 integers"""
    return If(a < b, a, b)


@Subroutine(TealType.uint64)
def saturate(n, upper_limit, lower_limit) -> Expr:
    """Produces an output that is the value of n bounded to the upper and lower
    saturation values. The upper and lower limits are specified by the
    parameters upper_limit and lower_limit."""
    return (
        If(n >= upper_limit)
        .Then(Return(upper_limit))
        .ElseIf(n <= lower_limit)
        .Then(Return(lower_limit))
        .Else(Return(n))
    )


@Subroutine(TealType.uint64)
def div_ceil(a, b) -> Expr:
    """Returns the result of division rounded up to the next integer

    Args:
        a: uint64 numerator for the operation
        b: uint64 denominator for the operation

    Returns:
        uint64 result of a truncated division + 1

    """
    q = a / b
    return If(a % b > Int(0), q + Int(1), q)


@Subroutine(TealType.uint64)
def pow10(x) -> Expr:
    """
    Returns 10^x, useful for things like total supply of an asset

    """
    return Exp(Int(10), x)


@Subroutine(TealType.uint64)
def factorial(x):
    """factorial returns x! = x * x-1 * x-2 * ...,
    for a 64bit integer, the max possible value is maxes out at 20

    Args:
        x: uint64 to call evaluate

    Returns:
        uint64 representing the factorial of the argument passed

    """
    return If(x == Int(1), x, x * factorial(x - Int(1)))


@Subroutine(TealType.bytes)
def wide_factorial(x):
    """factorial returns x! = x * x-1 * x-2 * ...,

    Args:
        x: bytes to evaluate as an integer

    Returns:
        bytes representing the integer that is the result of the factorial applied on the argument passed

    """
    return If(
        BitLen(x) == Int(1), x, BytesMul(x, wide_factorial(BytesMinus(x, Itob(Int(1)))))
    )


@Subroutine(TealType.bytes)
def wide_power(x, n):
    """wide_power returns the result of x^n evaluated using expw and combining the hi/low uint64s into a byte string

    Args:
        x: uint64 base for evaluation
        n: uint64 power to apply as exponent

    Returns:
        bytes representing the high and low bytes of a wide power evaluation

    """
    return Seq(InlineAssembly("expw", x, n), stack_to_wide())


def exponential(x, n):
    """exponential approximates e**x for n iterations

    TODO: currently this is scaled to 1000 first then scaled back. A better implementation should include the use of ufixed in abi types

    Args:
        x: The exponent to apply
        n: The number of iterations, more is better appx but costs ops

    Returns:
        uint64 that is the result of raising e**x

    """
    _scale = Itob(Int(1000))

    @Subroutine(TealType.bytes)
    def _impl(x, f, n):
        return If(
            n == Int(1),
            BytesAdd(_scale, BytesMul(x, _scale)),
            BytesAdd(
                _impl(x, BytesDiv(f, Itob(n)), n - Int(1)),
                BytesDiv(BytesMul(_scale, wide_power(bytes_to_int(x), n)), f),
            ),
        )

    return bytes_to_int(BytesDiv(_impl(Itob(x), wide_factorial(Itob(n)), n), _scale))


# @Subroutine(TealType.uint64)
# def log2(x):
#    """log2 is currently an alias for BitLen
#
#    TODO: implement with ufixed
#
#    """
#    return BitLen(x)  # Only returns integral component
#
#
# @Subroutine(TealType.uint64)
# def ln(x):
#    """Returns natural log of x for integer passed
#
#    This is heavily truncated since log2 does not return the fractional component yet
#
#    TODO: implement with ufixed
#
#    Args:
#        x: uint64 on which to take the natural log
#
#    Returns:
#        uint64 as the natural log of the value passed.
#    """
#    return (log2(x) * scale) / log2_e
#
#
# @Subroutine(TealType.uint64)
# def log10(x):
#    """Returns log base 10 of the integer passed
#
#    uses log10(x) = log2(x)/log2(10) identity
#
#    TODO: implement with ufixed
#
#    Args:
#        x: uint64  on which to take the log base 10
#
#    Returns:
#        uint64 as the log10 of the value passed
#
#    """
#    return (log2(x) * scale) / log2_10


@Subroutine(TealType.uint64)
def bytes_to_int(x):
    return If(Len(x) < Int(8), Btoi(x), ExtractUint64(x, Len(x) - Int(8)))


@Subroutine(TealType.bytes)
def stack_to_wide():
    """stack_to_wide returns the combination of the high and low integers returned from a wide math operation as bytes"""
    h = ScratchSlot()
    l = ScratchSlot()
    return Seq(
        l.store(),
        h.store(),  # Take the low and high ints off the stack and combine them
        Concat(Itob(h.load()), Itob(l.load())),
    )
