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


_page_size = 128 - 1  # 128 is max local storage bytes - 1 byte for key
page_size = Int(_page_size)


def intkey(i, start) -> Expr:
    return Extract(Itob(i + start), Int(7), Int(1))


def _key_and_offset(idx: Int) -> Tuple[Int, Int]:
    return idx / page_size, idx % page_size


class LocalBlob:
    """
    Blob is a class holding static methods to work with the local storage of an account as a binary large object

    The `zero` method must be called on an account on opt in and the schema of the local storage should be 16 bytes
    """

    def __init__(self, max_keys: int, start_key: int = 0):
        self.start_key = Int(start_key)
        # TODO: if max_keys == 16 and start_key == 1, we overflow
        assert max_keys <= 16 - start_key

        self._max_keys = max_keys
        self._max_bytes = self._max_keys * _page_size
        self._max_bits = self._max_bytes * 8

        self.max_keys = Int(self._max_keys)
        self.max_bytes = Int(self._max_bytes)

    def zero(self, acct) -> Expr:
        """
        initializes local state of an account to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size

        """

        @Subroutine(TealType.none)
        def _impl(acct):
            i = ScratchVar()
            init = i.store(self.start_key)
            cond = i.load() < self.max_keys
            iter = i.store(i.load() + Int(1))
            return For(init, cond, iter).Do(
                App.localPut(
                    acct, intkey(i.load(), self.start_key), BytesZero(page_size)
                )
            )

        return _impl(acct)

    def get_byte(self, acct, idx):
        """
        Get a single byte from local storage of an account by index
        """

        @Subroutine(TealType.uint64)
        def _impl(acct, idx):
            key, offset = _key_and_offset(idx)
            return GetByte(App.localGet(acct, intkey(key, self.start_key)), offset)

        return _impl(acct, idx)

    def set_byte(self, acct, idx, byte):
        """
        Set a single byte from local storage of an account by index
        """

        @Subroutine(TealType.none)
        def _impl(acct, idx, byte):
            key, offset = _key_and_offset(idx)
            return App.localPut(
                acct,
                intkey(key, self.start_key),
                SetByte(App.localGet(acct, intkey(key, self.start_key)), offset, byte),
            )

        return _impl(acct, idx, byte)

    def read(self, acct, bstart, bend) -> Expr:
        """
        read bytes between bstart and bend from local storage of an account by index
        """

        @Subroutine(TealType.bytes)
        def _impl(acct, bstart, bend):
            start_key, start_offset = _key_and_offset(bstart)
            stop_key, stop_offset = _key_and_offset(bend)

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
                                    App.localGet(
                                        acct, intkey(key.load(), self.start_key)
                                    ),
                                    start.load(),
                                    stop.load(),
                                ),
                            )
                        ),
                    )
                ),
                buff.load(),
            )

        return _impl(acct, bstart, bend)

    def write(self, acct, bstart, buff) -> Expr:
        """
        write bytes between bstart and len(buff) to local storage of an account
        """

        @Subroutine(TealType.uint64)
        def _impl(acct, bstart, buff):

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
                        App.localPut(
                            acct,
                            intkey(key.load(), self.start_key),
                            If(
                                Or(stop.load() != page_size, start.load() != Int(0))
                            )  # Its a partial write
                            .Then(
                                Seq(
                                    delta.store(stop.load() - start.load()),
                                    Concat(
                                        Substring(
                                            App.localGet(
                                                acct, intkey(key.load(), self.start_key)
                                            ),
                                            Int(0),
                                            start.load(),
                                        ),
                                        Extract(buff, written.load(), delta.load()),
                                        Substring(
                                            App.localGet(
                                                acct, intkey(key.load(), self.start_key)
                                            ),
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

        return _impl(acct, bstart, buff)
