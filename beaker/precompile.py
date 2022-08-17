from pyteal import Expr, Bytes, Addr
from algosdk.source_map import SourceMap

from beaker.logic_signature import LogicSignature


class Precompile:
    def __init__(self, lsig_type: type[LogicSignature]):
        self.lsig_type = lsig_type

        self.binary = None
        self.addr = None
        self.map = None

    def teal(self, *args) -> str:
        return self.lsig_type(*args).program

    def set_compiled(self, binary: bytes, addr: str, map: SourceMap):
        self.binary = binary
        self.addr = addr
        self.map = map

    def address(self) -> Expr:
        return Addr(self.addr)

    # def template_address(key: TealType.bytes):
    #    return Sha512_256(
    #        Concat(
    #            Bytes(consts.PROGRAM_DOMAIN_SEPARATOR),
    #            Extract(
    #                sig_bytes, Int(0), key_idx
    #            ),  # Take the bytes up to where the key should be
    #            encode_uvarint(
    #                Len(key), Bytes("")
    #            ),  # The length of the bytestring is encoded as uvarint
    #            key,
    #            Suffix(
    #                sig_bytes, Len(sig_bytes) - key_idx - Int(1)
    #            ),  # append the bytes from the key onward
    #        )
    #    )
