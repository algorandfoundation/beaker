from typing import Optional
from pyteal import (
    App,
    Bytes,
    Concat,
    Expr,
    Extract,
    For,
    GetByte,
    If,
    Int,
    Len,
    Or,
    ScratchVar,
    Seq,
    SetByte,
    Subroutine,
    Substring,
    TealType,
)

from beaker.lib.inline import InlineAssembly
from beaker.lib.storage.blob import BLOB_PAGE_SIZE, EMPTY_PAGE, Blob
from beaker.consts import MAX_GLOBAL_STATE


class GlobalBlob(Blob):
    def __init__(self, /, *, keys: Optional[int | list[int]] = None):
        super().__init__(MAX_GLOBAL_STATE, keys=keys)

    def zero(self) -> Expr:
        """
        initializes global state of an application to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size
        """

        @Subroutine(TealType.none)
        def zero_impl() -> Expr:
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
            return InlineAssembly(zloop, EMPTY_PAGE, self.max_keys, type=TealType.none)

        return zero_impl()

    def get_byte(self, idx: Expr) -> Expr:
        """
        Get a single byte from global storage of an application by index
        """

        @Subroutine(TealType.uint64)
        def get_byte_impl(idx: Expr) -> Expr:
            return GetByte(
                App.globalGet(self._key(self._key_idx(idx))), self._offset_for_idx(idx)
            )

        return get_byte_impl(idx)

    def set_byte(self, idx: Expr, byte: Expr) -> Expr:
        """
        Set a single byte from global storage of an application by index
        """

        @Subroutine(TealType.none)
        def set_byte_impl(idx: Expr, byte: Expr) -> Expr:
            return Seq(
                (key := ScratchVar()).store(self._key(self._key_idx(idx))),
                App.globalPut(
                    key.load(),
                    SetByte(App.globalGet(key.load()), self._offset_for_idx(idx), byte),
                ),
            )

        return set_byte_impl(idx, byte)

    def read(self, bstart: Expr, bstop: Expr) -> Expr:
        """
        read bytes between bstart and bend from global storage of an application by index
        """

        @Subroutine(TealType.bytes)
        def read_impl(bstart: Expr, bstop: Expr) -> Expr:
            start_key = self._key_idx(bstart)
            start_offset = self._offset_for_idx(bstart)

            stop_key = self._key_idx(bstop)
            stop_offset = self._offset_for_idx(bstop)

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
                        stop.store(
                            If(key.load() == stop_key, stop_offset, BLOB_PAGE_SIZE)
                        ),
                        buff.store(
                            Concat(
                                buff.load(),
                                Substring(
                                    App.globalGet(self._key(key.load())),
                                    start.load(),
                                    stop.load(),
                                ),
                            )
                        ),
                    )
                ),
                buff.load(),
            )

        return read_impl(bstart, bstop)

    def write(self, bstart: Expr, buff: Expr) -> Expr:
        """
        write bytes between bstart and len(buff) to global storage of an application
        """

        @Subroutine(TealType.none)
        def write_impl(bstart: Expr, buff: Expr) -> Expr:
            start_key = self._key_idx(bstart)
            start_offset = self._offset_for_idx(bstart)

            stop_key = self._key_idx(bstart + Len(buff))
            stop_offset = self._offset_for_idx(bstart + Len(buff))

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
                        stop.store(
                            If(key.load() == stop_key, stop_offset, BLOB_PAGE_SIZE)
                        ),
                        App.globalPut(
                            self._key(key.load()),
                            If(
                                Or(
                                    stop.load() != BLOB_PAGE_SIZE,
                                    start.load() != Int(0),
                                )
                            )  # Its a partial write
                            .Then(
                                Seq(
                                    delta.store(stop.load() - start.load()),
                                    Concat(
                                        Substring(
                                            App.globalGet(self._key(key.load())),
                                            Int(0),
                                            start.load(),
                                        ),
                                        Extract(buff, written.load(), delta.load()),
                                        Substring(
                                            App.globalGet(self._key(key.load())),
                                            stop.load(),
                                            BLOB_PAGE_SIZE,
                                        ),
                                    ),
                                )
                            )
                            .Else(
                                Seq(
                                    delta.store(BLOB_PAGE_SIZE),
                                    Extract(buff, written.load(), BLOB_PAGE_SIZE),
                                )
                            ),
                        ),
                        written.store(written.load() + delta.load()),
                    )
                ),
            )

        return write_impl(bstart, buff)
