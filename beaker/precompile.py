from dataclasses import dataclass, field
from pyteal import *
from algosdk.source_map import SourceMap
from algosdk.future.transaction import LogicSigAccount
from algosdk.atomic_transaction_composer import LogicSigTransactionSigner
from beaker.consts import PROGRAM_DOMAIN_SEPARATOR
from beaker.logic_signature import LogicSignature
from beaker.lib.strings import encode_uvarint


@dataclass
class TemplateValue:
    name: str = field(kw_only=True)
    is_bytes: bool = field(kw_only=True)
    line: int = field(kw_only=True)
    pc: int = 0


TMPL_PREFIX = "TMPL_"
PUSH_BYTES = "pushbytes"
PUSH_INT = "pushint"


def py_encode_uvarint(integer: int) -> bytes:
    """Encodes an integer as an uvarint.
    :param integer: the integer to encode
    :return: bytes containing the integer encoded as an uvarint
    """

    def to_byte(integer: int) -> int:
        return integer & 0b1111_1111

    buffer: bytearray = bytearray()

    while integer >= 0b1000_0000:
        buffer.append(to_byte(integer) | 0b1000_0000)
        integer >>= 7

    buffer.append(to_byte(integer))

    return bytes(buffer)


class Precompile:
    def __init__(self, lsig: LogicSignature):
        self.lsig = lsig

        self.program = lsig.program

        self.binary = None
        self.addr = None
        self.map = None

        self.template_values: list[TemplateValue] = []

        # Replace the program text with 0 value
        lines = self.program.splitlines()
        for idx, line in enumerate(lines):
            if TMPL_PREFIX in line:
                op, name, _, _ = line.split(" ")
                tv = TemplateValue(
                    name=name[len(TMPL_PREFIX) :], is_bytes=op == PUSH_BYTES, line=idx
                )
                lines[idx] = line.replace(name, '""' if tv.is_bytes else "0")
                self.template_values.append(tv)
        self.program = "\n".join(lines)

    def teal(self) -> str:
        return self.program

    def set_compiled(self, binary: bytes, addr: str, map: SourceMap):
        self.binary = binary
        self.addr = addr
        self.map = map

        self.binary_bytes = Bytes(binary)

        for tv in self.template_values:
            tv.pc = self.map.get_pcs_for_line(tv.line)[0] + 1

    def address(self) -> Expr:
        return Addr(self.addr)

    def signer(self) -> LogicSigTransactionSigner:
        return LogicSigTransactionSigner(LogicSigAccount(self.binary))

    def populate_template(self, *args)->bytes:
        assert self.binary is not None
        assert len(self.template_values) > 0
        assert len(args) == len(self.template_values)

        print(list(self.binary))
        populated_binary = list(self.binary).copy()
        pos, offset = self.template_values[0].pc, 0

        for idx, tv in enumerate(self.template_values):
            print(offset, pos)
            if tv.is_bytes:
                curr_val = py_encode_uvarint(len(args[idx])) + args[idx]
            else:
                curr_val = py_encode_uvarint(args[idx])

            populated_binary[pos:pos+1] = curr_val
            offset += len(curr_val) - 1
            pos = tv.pc + offset

        return bytes(populated_binary)

    def template_signer(self, *args) -> LogicSigTransactionSigner:
        return LogicSigTransactionSigner(LogicSigAccount(self.populate_template(*args)))

    def template_address(self, *args: Expr) -> Expr:
        populate_program: list[Expr] = [
            (offset := ScratchVar(TealType.uint64)).store(Int(0)),
            (curr_val := ScratchVar(TealType.bytes)).store(Bytes("")),
            (buff := ScratchVar(TealType.bytes)).store(Bytes("")),
        ]

        last_pc = 0
        for idx, tc in enumerate(self.template_values):

            if tc.is_bytes:
                populate_program.append(
                    curr_val.store(
                        Concat(encode_uvarint(Len(args[idx]), Bytes("")), args[idx])
                    ),
                )
            else:
                populate_program.append(
                    curr_val.store(encode_uvarint(args[idx], Bytes(""))),
                )

            populate_program += [
                buff.store(
                    Concat(
                        buff.load(),
                        Extract(
                            self.binary_bytes,
                            Int(last_pc) + offset.load(),
                            Int(tc.pc) + offset.load(),
                        ),
                        curr_val.load(),
                    )
                ),
                offset.store(offset.load() + Len(curr_val.load()) - Int(1)),
            ]

            last_pc = tc.pc

        ## append the bytes from the last template variable to the end
        populate_program += [
            buff.store(
                Concat(
                    buff.load(), Suffix(self.binary_bytes, Int(last_pc) + offset.load())
                )
            ),
            buff.load(),
        ]

        return Sha512_256(
            Concat(Bytes(PROGRAM_DOMAIN_SEPARATOR), Seq(*populate_program))
        )
