from pyteal import (
    Assert,
    BitLen,
    Btoi,
    Bytes,
    BytesDiv,
    BytesGt,
    BytesMod,
    Concat,
    Extract,
    GetByte,
    If,
    Int,
    Itob,
    Len,
    ScratchVar,
    Seq,
    Subroutine,
    Substring,
    TealType,
)

from beaker.lib.math import Pow10

# Magic number to convert between ascii chars and integers
_ascii_zero = 48
_ascii_nine = _ascii_zero + 9
ascii_zero = Int(_ascii_zero)
ascii_nine = Int(_ascii_nine)


@Subroutine(TealType.uint64, name="ascii_to_int")
def AsciiToInt(arg):  # noqa: N802
    """AsciiToInt converts the integer representing a character in ascii to the actual integer it represents

    Args:
        arg: uint64 in the range 48-57 that is to be converted to an integer

    Returns:
        uint64 that is the value the ascii character passed in represents

    """
    return Seq(Assert(arg >= ascii_zero), Assert(arg <= ascii_nine), arg - ascii_zero)


@Subroutine(TealType.bytes, name="int_to_ascii")
def IntToAscii(arg):  # noqa: N802
    """int_to_ascii converts an integer to the ascii byte that represents it"""
    return Extract(Bytes("0123456789"), arg, Int(1))


@Subroutine(TealType.uint64, name="atoi")
def Atoi(a):  # noqa: N802
    """Atoi converts a byte string representing a number to the integer value it represents"""
    return If(
        Len(a) > Int(0),
        (AsciiToInt(GetByte(a, Int(0))) * Pow10(Len(a) - Int(1)))
        + Atoi(Substring(a, Int(1), Len(a))),
        Int(0),
    )


@Subroutine(TealType.bytes, name="itoa")
def Itoa(i):  # noqa: N802
    """Itoa converts an integer to the ascii byte string it represents"""
    return If(
        i == Int(0),
        Bytes("0"),
        Concat(
            If(i / Int(10) > Int(0), Itoa(i / Int(10)), Bytes("")),
            IntToAscii(i % Int(10)),
        ),
    )


@Subroutine(TealType.bytes, name="witoa")
def Witoa(i):  # noqa: N802
    """Witoa converts a byte string interpreted as an integer to the ascii byte string it represents"""
    return If(
        BitLen(i) == Int(0),
        Bytes("0"),
        Concat(
            If(
                BytesGt(BytesDiv(i, Bytes("base16", "A0")), Bytes("base16", "A0")),
                Witoa(BytesDiv(i, Bytes("base16", "A0"))),
                Bytes(""),
            ),
            IntToAscii(Btoi(BytesMod(i, Bytes("base16", "A0")))),
        ),
    )


@Subroutine(TealType.bytes, name="head")
def Head(s):  # noqa: N802
    """Head gets the first byte from a bytestring, returns as bytes"""
    return Extract(s, Int(0), Int(1))


@Subroutine(TealType.bytes, name="tail")
def Tail(s):  # noqa: N802
    """Tail returns the string with the first character removed"""
    return Substring(s, Int(1), Len(s))


@Subroutine(TealType.bytes, name="suffix")
def Suffix(s, n):  # noqa: N802
    """Suffix returns the last n bytes of a given byte string"""
    return Substring(s, Len(s) - n, Len(s))


@Subroutine(TealType.bytes, name="prefix")
def Prefix(s, n):  # noqa: N802
    """Prefix returns the first n bytes of a given byte string"""
    return Substring(s, Int(0), n)


@Subroutine(TealType.bytes, name="rest")
def Rest(s, n):  # noqa: N802
    """Rest returns the remaining bytes after the first n bytes of a given byte string"""
    return Substring(s, n, Len(s))


@Subroutine(TealType.bytes)
def encode_uvarint_impl(val, b):
    buff = ScratchVar()
    return Seq(
        buff.store(b),
        Concat(
            buff.load(),
            If(
                val >= Int(128),
                encode_uvarint_impl(
                    val >> Int(7),
                    Extract(Itob((val & Int(255)) | Int(128)), Int(7), Int(1)),
                ),
                Extract(Itob(val & Int(255)), Int(7), Int(1)),
            ),
        ),
    )


def EncodeUVarInt(val):  # noqa: N802
    """
    Returns the uvarint encoding of an integer

    Useful in the case that the bytecode for a contract is being populated, since
    integers in a contract are uvarint encoded
    """

    return encode_uvarint_impl(val, Bytes(""))
