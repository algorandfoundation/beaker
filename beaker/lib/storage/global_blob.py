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

from beaker.consts import MAX_GLOBAL_STATE
from beaker.lib.inline import InlineAssembly
from beaker.lib.storage.blob import BLOB_PAGE_SIZE, EMPTY_PAGE, Blob


class GlobalBlob(Blob):
    def __init__(self, *, keys: int | list[int] = MAX_GLOBAL_STATE):
        super().__init__(keys=keys)

        @Subroutine(TealType.none)
        def set_byte_impl(idx: Expr, byte: Expr) -> Expr:
            return Seq(
                (key := ScratchVar()).store(self._key(self._key_idx(idx))),
                App.globalPut(
                    key.load(),
                    SetByte(App.globalGet(key.load()), self._offset_for_idx(idx), byte),
                ),
            )

        self._set_byte_impl = set_byte_impl

        @Subroutine(TealType.none)
        def zero_impl() -> Expr:
            zloop = """
    zero_loop:
        int 1
        -               // ["00"*page_size, key-1]
        dup2            // ["00"*page_size, key, "00"*page_size, key]
        itob            // ["00"*page_size, key, "00"*page_size, itob(key)]
        extract 7 1     // ["00"*page_size, key, "00"*page_size, itob(key)[-1]]
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

        self._zero_impl = zero_impl

        @Subroutine(TealType.uint64)
        def get_byte_impl(idx: Expr) -> Expr:
            return GetByte(
                App.globalGet(self._key(self._key_idx(idx))), self._offset_for_idx(idx)
            )

        self._get_byte_impl = get_byte_impl

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
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, BLOB_PAGE_SIZE)),
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
                ),
                buff.load(),
            )

        self._read_impl = read_impl

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
                    start.store(If(key.load() == start_key, start_offset, Int(0))),
                    stop.store(If(key.load() == stop_key, stop_offset, BLOB_PAGE_SIZE)),
                    App.globalPut(
                        self._key(key.load()),
                        If(
                            Or(
                                stop.load() != BLOB_PAGE_SIZE,
                                start.load() != Int(0),
                            )
                        )  # Its a partial write
                        .Then(
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
                        .Else(
                            delta.store(BLOB_PAGE_SIZE),
                            Extract(buff, written.load(), BLOB_PAGE_SIZE),
                        ),
                    ),
                    written.store(written.load() + delta.load()),
                ),
            )

        self._write_impl = write_impl

    def zero(self) -> Expr:
        """
        initializes global state of an application to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size
        """
        return self._zero_impl()

    def get_byte(self, idx: Expr) -> Expr:
        """
        Get a single byte from global storage of an application by index
        """
        return self._get_byte_impl(idx)

    def set_byte(self, idx: Expr, byte: Expr) -> Expr:
        """
        Set a single byte from global storage of an application by index
        """
        return self._set_byte_impl(idx, byte)

    def read(self, bstart: Expr, bstop: Expr) -> Expr:
        """
        read bytes between bstart and bend from global storage
        of an application by index
        """
        return self._read_impl(bstart, bstop)

    def write(self, bstart: Expr, buff: Expr) -> Expr:
        """
        write bytes between bstart and len(buff) to global storage of an application
        """
        return self._write_impl(bstart, buff)
