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


class LocalBlob:
    """
    Blob is a class holding static methods to work with the local storage of an account as a binary large object

    The `zero` method must be called on an account on opt in and the schema of the local storage should be 16 bytes
    """

    def __init__(self, keys: list[int] = None):
        if keys is None or len(keys) == 0:
            keys = [x for x in range(16)]

        assert len(keys) <= 16
        assert max(keys) <= 255
        assert sorted(keys) == keys

        self.byte_keys = [key.to_bytes(1, "big") for key in keys]
        self.byte_key_str = Bytes("base16", b"".join(self.byte_keys).hex())

        self.int_keys = [Int(key) for key in keys]
        self.start_key = self.int_keys[0]

        self._max_keys = len(keys)
        self._max_bytes = self._max_keys * _page_size
        self._max_bits = self._max_bytes * 8

        self.max_keys = Int(self._max_keys)
        self.max_bytes = Int(self._max_bytes)

    def _key(self, i) -> Expr:
        return Extract(self.byte_key_str, i, Int(1))

    def _key_idx(self, idx: Int) -> Expr:
        return idx / page_size

    def _offset_for_idx(self, idx: Int) -> Expr:
        return idx % page_size

    def zero(self, acct) -> Expr:
        """
        initializes local state of an account to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size

        """

        @Subroutine(TealType.none)
        def _impl(acct):
            writes: list[Expr] = [
                App.localPut(acct, Bytes(bk), BytesZero(page_size))
                for bk in self.byte_keys
            ]
            return Seq(*writes)

        return _impl(acct)

    def get_byte(self, acct, idx):
        """
        Get a single byte from local storage of an account by index
        """

        @Subroutine(TealType.uint64)
        def _impl(acct, idx):
            return GetByte(
                App.localGet(acct, self._key(self._key_idx(idx))),
                self._offset_for_idx(idx),
            )

        return _impl(acct, idx)

    def set_byte(self, acct, idx, byte):
        """
        Set a single byte from local storage of an account by index
        """

        @Subroutine(TealType.none)
        def _impl(acct, idx, byte):
            return Seq(
                (key := ScratchVar()).store(self._key(self._key_idx(idx))),
                App.localPut(
                    acct,
                    key.load(),
                    SetByte(
                        App.localGet(acct, key.load()), self._offset_for_idx(idx), byte
                    ),
                ),
            )

        return _impl(acct, idx, byte)

    def read(self, acct, bstart, bend) -> Expr:
        """
        read bytes between bstart and bend from local storage of an account by index
        """

        @Subroutine(TealType.bytes)
        def _impl(acct, bstart, bend):
            start_key = self._key_idx(bstart)
            start_offset = self._offset_for_idx(bstart)
            stop_key = self._key_idx(bend)
            stop_offset = self._offset_for_idx(bend)

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
                                    App.localGet(acct, self._key(key.load())),
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
                        stop.store(If(key.load() == stop_key, stop_offset, page_size)),
                        App.localPut(
                            acct,
                            self._key(key.load()),
                            If(
                                Or(stop.load() != page_size, start.load() != Int(0))
                            )  # Its a partial write
                            .Then(
                                Seq(
                                    delta.store(stop.load() - start.load()),
                                    Concat(
                                        Substring(
                                            App.localGet(acct, self._key(key.load())),
                                            Int(0),
                                            start.load(),
                                        ),
                                        Extract(buff, written.load(), delta.load()),
                                        Substring(
                                            App.localGet(acct, self._key(key.load())),
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
