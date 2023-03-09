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
    Txn,
)

from beaker.consts import MAX_LOCAL_STATE
from beaker.lib.storage.blob import BLOB_PAGE_SIZE, EMPTY_PAGE, Blob


class LocalBlob(Blob):
    """
    Blob is a class holding static methods to work with the local storage of an account
    as a binary large object

    Note: The `zero` method must be called on an account on opt in and the schema
    of the local storage should be 16 bytes
    """

    def __init__(self, *, keys: int | list[int] = MAX_LOCAL_STATE):
        super().__init__(keys=keys)

        @Subroutine(TealType.none)
        def zero_impl(acct: Expr) -> Expr:
            return Seq(
                *[App.localPut(acct, Bytes(bk), EMPTY_PAGE) for bk in self.byte_keys]
            )

        self._zero_impl = zero_impl

        @Subroutine(TealType.uint64)
        def get_byte_impl(acct: Expr, idx: Expr) -> Expr:
            return GetByte(
                App.localGet(acct, self._key(self._key_idx(idx))),
                self._offset_for_idx(idx),
            )

        self._get_byte_impl = get_byte_impl

        @Subroutine(TealType.none)
        def set_byte_impl(acct: Expr, idx: Expr, byte: Expr) -> Expr:
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

        self._set_byte_impl = set_byte_impl

        @Subroutine(TealType.bytes)
        def read_impl(acct: Expr, bstart: Expr, bend: Expr) -> Expr:
            start_key_idx = self._key_idx(bstart)
            start_offset = self._offset_for_idx(bstart)

            stop_key_idx = self._key_idx(bend)
            stop_offset = self._offset_for_idx(bend)

            key_idx = ScratchVar()
            buff = ScratchVar()

            start = ScratchVar()
            stop = ScratchVar()

            init = key_idx.store(start_key_idx)
            cond = key_idx.load() <= stop_key_idx
            incr = key_idx.store(key_idx.load() + Int(1))

            return Seq(
                buff.store(Bytes("")),
                For(init, cond, incr).Do(
                    start.store(
                        If(key_idx.load() == start_key_idx, start_offset, Int(0))
                    ),
                    stop.store(
                        If(
                            key_idx.load() == stop_key_idx,
                            stop_offset,
                            BLOB_PAGE_SIZE,
                        )
                    ),
                    buff.store(
                        Concat(
                            buff.load(),
                            Substring(
                                App.localGet(acct, self._key(key_idx.load())),
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
        def write_impl(acct: Expr, bstart: Expr, buff: Expr) -> Expr:

            start_key_idx = self._key_idx(bstart)
            start_offset = self._offset_for_idx(bstart)

            stop_key_idx = self._key_idx(bstart + Len(buff))
            stop_offset = self._offset_for_idx(bstart + Len(buff))

            key_idx = ScratchVar()
            start = ScratchVar()
            stop = ScratchVar()
            written = ScratchVar()

            init = key_idx.store(start_key_idx)
            cond = key_idx.load() <= stop_key_idx
            incr = key_idx.store(key_idx.load() + Int(1))

            delta = ScratchVar()

            return Seq(
                written.store(Int(0)),
                For(init, cond, incr).Do(
                    Seq(
                        start.store(
                            If(key_idx.load() == start_key_idx, start_offset, Int(0))
                        ),
                        stop.store(
                            If(
                                key_idx.load() == stop_key_idx,
                                stop_offset,
                                BLOB_PAGE_SIZE,
                            )
                        ),
                        App.localPut(
                            acct,
                            self._key(key_idx.load()),
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
                                        App.localGet(acct, self._key(key_idx.load())),
                                        Int(0),
                                        start.load(),
                                    ),
                                    Extract(buff, written.load(), delta.load()),
                                    Substring(
                                        App.localGet(acct, self._key(key_idx.load())),
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
                    )
                ),
            )

        self._write_impl = write_impl

    def zero(self, acct: Expr = Txn.sender()) -> Expr:  # noqa: B008
        """
        initializes local state of an account to all zero bytes

        This allows us to be lazy later and _assume_ all the strings are the same size

        """
        return self._zero_impl(acct)

    def get_byte(self, idx: Expr, acct: Expr = Txn.sender()) -> Expr:  # noqa: B008
        """
        Get a single byte from local storage of an account by index
        """
        return self._get_byte_impl(acct, idx)

    def set_byte(
        self,
        idx: Expr,
        byte: Expr,
        acct: Expr = Txn.sender(),  # noqa: B008
    ) -> Expr:
        """
        Set a single byte from local storage of an account by index
        """
        return self._set_byte_impl(acct, idx, byte)

    def read(
        self,
        bstart: Expr,
        bend: Expr,
        acct: Expr = Txn.sender(),  # noqa: B008
    ) -> Expr:
        """
        read bytes between bstart and bend from local storage of an account by index
        """
        return self._read_impl(acct, bstart, bend)

    def write(
        self,
        bstart: Expr,
        buff: Expr,
        acct: Expr = Txn.sender(),  # noqa: B008
    ) -> Expr:
        """
        write bytes between bstart and len(buff) to local storage of an account
        """
        return self._write_impl(acct, bstart, buff)
