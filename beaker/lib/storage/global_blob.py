from typing import Tuple

from pyteal import (
    App,
    Bytes,
    BytesZero,
    Concat,
    Expr,
    Extract,
    For,
    GetByte,
    If,
    Int,
    Itob,
    Len,
    Or,
    ScratchVar,
    Seq,
    SetByte,
    Subroutine,
    Substring,
    TealType,
)

from ..inline import InlineAssembly

_max_keys = 64
_page_size = 128 - 1  # need 1 byte for key
_max_bytes = _max_keys * _page_size
_max_bits = _max_bytes * 8

max_keys = Int(_max_keys)
page_size = Int(_page_size)
max_bytes = Int(_max_bytes)


def _key_and_offset(idx: Int) -> Tuple[Int, Int]:
    return idx / page_size, idx % page_size


@Subroutine(TealType.bytes)
def intkey(i: Expr) -> Expr:
    return Extract(Itob(i), Int(7), Int(1))


# TODO: Add Keyspace range?
class GlobalBlob:
    """
    Blob is a class holding static methods to work with the global storage of an application as a binary large object

    The `zero` method must be called on an application on opt in and the schema of the global storage should be 16 bytes
    """

    @staticmethod
    @Subroutine(TealType.none)
    def zero() -> Expr:
        """
        initializes global state of an application to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size
        """

        # Expects bzero'd, max_keys
        zloop = """
zero_loop:
    int 1
    -               // ["00"*page_size, key-1]
    dup2            // ["00"*page_size, key, "00"*page_size, key]
    itob            // ["00"*page_size, key, "00"*page_size, itob(key)]
    extract 7 1     // ["00"*page_size, key, "00"*page_size, itob(key)[-1]] get the last byte of the int
    swap            // ["00"*page_size, key, itob(key)[-1], "00"*page_size]
    app_global_put  // ["00"*page_size, key]  (removes top 2 elements)
    dup             // ["00"*page_size, key-1, key-1]
    bnz zero_loop   // start loop over if key-1>0
    pop
    pop             // take extra junk off the stack
    retsub
callsub zero_loop
        """
        return InlineAssembly(zloop, BytesZero(page_size), max_keys, type=TealType.none)

    @staticmethod
    @Subroutine(TealType.uint64)
    def get_byte(idx):
        """
        Get a single byte from global storage of an application by index
        """
        key, offset = _key_and_offset(idx)
        return GetByte(App.globalGet(intkey(key)), offset)

    @staticmethod
    @Subroutine(TealType.none)
    def set_byte(idx, byte):
        """
        Set a single byte from global storage of an application by index
        """
        key, offset = _key_and_offset(idx)
        return App.globalPut(
            intkey(key), SetByte(App.globalGet(intkey(key)), offset, byte)
        )

    @staticmethod
    @Subroutine(TealType.bytes)
    def read(bstart, bstop) -> Expr:
        """
        read bytes between bstart and bend from global storage of an application by index
        """

        start_key, start_offset = _key_and_offset(bstart)
        stop_key, stop_offset = _key_and_offset(bstop)

        key = ScratchVar()
        buff = ScratchVar()

        start = ScratchVar()
        stop = ScratchVar()

        init = key.store(start_key)
        cond = key.load() <= stop_key
        incr = key.store(key.load() + Int(1))

        return Seq(
            buff.store(Bytes("")),
            For(init, cond, incr).Do(
                Seq(
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, page_size)),
                    buff.store(
                        Concat(
                            buff.load(),
                            Substring(
                                App.globalGet(intkey(key.load())),
                                start.load(),
                                stop.load(),
                            ),
                        )
                    ),
                )
            ),
            buff.load(),
        )

    @staticmethod
    @Subroutine(TealType.uint64)
    def write(bstart, buff) -> Expr:
        """
        write bytes between bstart and len(buff) to global storage of an application
        """

        start_key, start_offset = _key_and_offset(bstart)
        stop_key, stop_offset = _key_and_offset(bstart + Len(buff))

        key = ScratchVar()
        start = ScratchVar()
        stop = ScratchVar()
        written = ScratchVar()

        init = key.store(start_key)
        cond = key.load() <= stop_key
        incr = key.store(key.load() + Int(1))

        delta = ScratchVar()

        return Seq(
            written.store(Int(0)),
            For(init, cond, incr).Do(
                Seq(
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, page_size)),
                    App.globalPut(
                        intkey(key.load()),
                        If(
                            Or(stop.load() != page_size, start.load() != Int(0))
                        )  # Its a partial write
                        .Then(
                            Seq(
                                delta.store(stop.load() - start.load()),
                                Concat(
                                    Substring(
                                        App.globalGet(intkey(key.load())),
                                        Int(0),
                                        start.load(),
                                    ),
                                    Extract(buff, written.load(), delta.load()),
                                    Substring(
                                        App.globalGet(intkey(key.load())),
                                        stop.load(),
                                        page_size,
                                    ),
                                ),
                            )
                        )
                        .Else(
                            Seq(
                                delta.store(page_size),
                                Extract(buff, written.load(), page_size),
                            )
                        ),
                    ),
                    written.store(written.load() + delta.load()),
                )
            ),
            written.load(),
        )
