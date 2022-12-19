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

from beaker.lib.math import pow10

# Magic number to convert between ascii chars and integers
_ascii_zero = 48
_ascii_nine = _ascii_zero + 9
ascii_zero = Int(_ascii_zero)
ascii_nine = Int(_ascii_nine)


@Subroutine(TealType.uint64)
def ascii_to_int(arg):
    """ascii_to_int converts the integer representing a character in ascii to the actual integer it represents

    Args:
        arg: uint64 in the range 48-57 that is to be converted to an integer

    Returns:
        uint64 that is the value the ascii character passed in represents

    """
    return Seq(Assert(arg >= ascii_zero), Assert(arg <= ascii_nine), arg - ascii_zero)


@Subroutine(TealType.bytes)
def int_to_ascii(arg):
    """int_to_ascii converts an integer to the ascii byte that represents it"""
    return Extract(Bytes("0123456789"), arg, Int(1))


@Subroutine(TealType.uint64)
def atoi(a):
    """atoi converts a byte string representing a number to the integer value it represents"""
    return If(
        Len(a) > Int(0),
        (ascii_to_int(GetByte(a, Int(0))) * pow10(Len(a) - Int(1)))
        + atoi(Substring(a, Int(1), Len(a))),
        Int(0),
    )


@Subroutine(TealType.bytes)
def itoa(i):
    """itoa converts an integer to the ascii byte string it represents"""
    return If(
        i == Int(0),
        Bytes("0"),
        Concat(
            If(i / Int(10) > Int(0), itoa(i / Int(10)), Bytes("")),
            int_to_ascii(i % Int(10)),
        ),
    )


@Subroutine(TealType.bytes)
def witoa(i):
    """witoa converts an byte string interpreted as an integer to the ascii byte string it represents"""
    return If(
        BitLen(i) == Int(0),
        Bytes("0"),
        Concat(
            If(
                BytesGt(BytesDiv(i, Bytes("base16", "A0")), Bytes("base16", "A0")),
                witoa(BytesDiv(i, Bytes("base16", "A0"))),
                Bytes(""),
            ),
            int_to_ascii(Btoi(BytesMod(i, Bytes("base16", "A0")))),
        ),
    )


@Subroutine(TealType.bytes)
def head(s):
    """head gets the first byte from a bytestring, returns as bytes"""
    return Extract(s, Int(0), Int(1))


@Subroutine(TealType.bytes)
def tail(s):
    """tail returns the string with the first character removed"""
    return Substring(s, Int(1), Len(s))


@Subroutine(TealType.bytes)
def suffix(s, n):
    """suffix returns the last n bytes of a given byte string"""
    return Substring(s, Len(s) - n, Len(s))


@Subroutine(TealType.bytes)
def prefix(s, n):
    """prefix returns the first n bytes of a given byte string"""
    return Substring(s, Int(0), n)


@Subroutine(TealType.bytes)
def rest(s, n):
    """prefix returns the first n bytes of a given byte string"""
    return Substring(s, n, Len(s))


def encode_uvarint(val):
    """
    Returns the uvarint encoding of an integer

    Useful in the case that the bytecode for a contract is being populated, since
    integers in a contract are uvarint encoded

    This subroutine is recursive, the first call should include
    the integer to be encoded and an empty bytestring

    """

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

    return encode_uvarint_impl(val, Bytes(""))
