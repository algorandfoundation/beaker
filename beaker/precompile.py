from dataclasses import dataclass, field
from typing import Optional
from pyteal import (
    Seq,
    Bytes,
    Expr,
    Addr,
    ScratchVar,
    TealType,
    TealTypeError,
    TealInputError,
    Int,
    Concat,
    Len,
    Substring,
    Suffix,
    Subroutine,
    Sha512_256,
)
from algosdk.source_map import SourceMap
from algosdk.future.transaction import LogicSigAccount
from algosdk.atomic_transaction_composer import LogicSigTransactionSigner
from beaker.consts import PROGRAM_DOMAIN_SEPARATOR
from beaker.logic_signature import LogicSignature
from beaker.lib.strings import encode_uvarint


@dataclass
class PrecompileTemplateValue:
    #: The name of the template variable
    name: str = field(kw_only=True)
    #: Whether or not this variable is bytes (if false, its uint64)
    is_bytes: bool = field(kw_only=True)
    #: The line number in the source TEAL this variable is present
    line: int = field(kw_only=True)
    #: The pc of the variable in the assembled bytecode
    pc: int = 0


#: The prefix for template variables that should be substituted
TMPL_PREFIX = "TMPL_"

#: The opcode that should be present just before the byte template variable
PUSH_BYTES = "pushbytes"
#: The opcode that should be present just before the uint64 template variable
PUSH_INT = "pushint"

#: The zero value for byte type
ZERO_BYTES = '""'
#: The zero value for uint64 type
ZERO_INT = "0"


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
    """
    Precompile allows a contract to signal that some LogicSignature should be
    fully compiled prior to trying to construct the approval and clear programs.
    """

    def __init__(self, lsig: LogicSignature):
        self.lsig = lsig

        self.program = lsig.program

        self.binary: Optional[bytes] = None
        self.addr: Optional[str] = None
        self.map: Optional[SourceMap] = None

        self.template_values: list[PrecompileTemplateValue] = []

        lines = self.program.splitlines()
        # Replace the teal program TMPL_* template variables with
        # the 0 value for the given type and save the list of TemplateValues
        for idx, line in enumerate(lines):
            if TMPL_PREFIX in line:
                op, name, _, _ = line.split(" ")
                tv = PrecompileTemplateValue(
                    name=name[len(TMPL_PREFIX) :], is_bytes=op == PUSH_BYTES, line=idx
                )
                lines[idx] = line.replace(name, ZERO_BYTES if tv.is_bytes else ZERO_INT)
                self.template_values.append(tv)

        self.program = "\n".join(lines)

    def _set_compiled(self, binary: bytes, addr: str, map: SourceMap):
        """
        Called by application_client to set the binary/addr/map for
        this precompile.
        """
        self.binary = binary
        self.addr = addr
        self.map = map

        self.binary_bytes = Bytes(binary)

        # Denote the pc for each template value
        for tv in self.template_values:
            # +1 to acount for the pushbytes/pushint op
            tv.pc = self.map.get_pcs_for_line(tv.line)[0] + 1

    def address(self) -> Expr:
        """
        address returns an expression for this Precompile.

        It will fail if any template_values are set.
        """

        assert self.binary is not None
        assert len(self.template_values) == 0
        if self.addr is None:
            raise TealInputError("No address defined for precompile lsig")

        return Addr(self.addr)

    def signer(self) -> LogicSigTransactionSigner:
        """
        signer returns a LogicSigTransactionSigner to be used with
        an ApplicationClient or AtomicTransactionComposer.

        It should only be used for non templated Precompiles.
        """
        return LogicSigTransactionSigner(LogicSigAccount(self.binary))

    def populate_template(self, *args) -> bytes:
        """
        populate_template returns the bytes resulting from patching the set of
        arguments passed into the blank binary

        The args passed should be of the same type and in the same order as the
        template values declared.
        """

        assert self.binary is not None
        assert len(self.template_values) > 0
        assert len(args) == len(self.template_values)

        # Get a copy of the binary so we can work on it in place
        populated_binary = list(self.binary).copy()
        # Any time we add bytes, we need to update the offset so the rest
        # of the pc values can be updated to account for the difference
        offset = 0
        for idx, tv in enumerate(self.template_values):
            arg: str | bytes | int = args[idx]

            if tv.is_bytes:
                if type(arg) is int:
                    raise TealTypeError(type(arg), bytes | str)

                if type(arg) is str:
                    arg = arg.encode("utf-8")

                assert type(arg) is bytes

                # Bytes are encoded as uvarint(len(bytes)) + bytes
                curr_val = py_encode_uvarint(len(arg)) + arg
            else:
                if type(arg) is not int:
                    raise TealTypeError(type(arg), int)
                # Ints are just the uvarint encoded number
                curr_val = py_encode_uvarint(arg)

            # update the working buffer to include the new value, replacing the current 0 value
            populated_binary[tv.pc + offset : tv.pc + offset + 1] = curr_val

            # update the offset with the length(value) - 1 to account for the existing 0 value
            # and help keep track of how to shift the pc later
            offset += len(curr_val) - 1

        return bytes(populated_binary)

    def template_signer(self, *args) -> LogicSigTransactionSigner:
        return LogicSigTransactionSigner(LogicSigAccount(self.populate_template(*args)))

    def populate_template_expr(self, *args: Expr) -> Expr:
        """
        populate_template_expr returns the Expr that will patch a
        blank binary given a set of arguments.

        It is called by ``template_address`` to return a Expr that
        can be used to compare with a sender given some arguments.
        """

        # To understand how this works, first look at the pure python one above
        # it should produce an identical output in terms of populated binary.
        # This function just reproduces the same effects in pyteal

        assert self.binary_bytes is not None
        assert len(self.template_values)
        assert len(args) == len(self.template_values)

        populate_program: list[Expr] = [
            (last_pos := ScratchVar(TealType.uint64)).store(Int(0)),
            (offset := ScratchVar(TealType.uint64)).store(Int(0)),
            (curr_val := ScratchVar(TealType.bytes)).store(Bytes("")),
            (buff := ScratchVar(TealType.bytes)).store(Bytes("")),
        ]

        for idx, tv in enumerate(self.template_values):
            # Add expressions to encode the values and insert them into the working buffer
            populate_program += [
                curr_val.store(Concat(encode_uvarint(Len(args[idx])), args[idx]))
                if tv.is_bytes
                else curr_val.store(encode_uvarint(args[idx])),
                buff.store(
                    Concat(
                        buff.load(),
                        Substring(
                            self.binary_bytes,
                            last_pos.load(),
                            Int(tv.pc),
                        ),
                        curr_val.load(),
                    )
                ),
                offset.store(offset.load() + Len(curr_val.load()) - Int(1)),
                last_pos.store(Int(tv.pc) + Int(1)),
            ]

        # append the bytes from the last template variable to the end
        populate_program += [
            buff.store(Concat(buff.load(), Suffix(self.binary_bytes, last_pos.load()))),
            buff.load(),
        ]

        @Subroutine(TealType.bytes)
        def populate_template_lsig():
            return Seq(*populate_program)

        return populate_template_lsig()

    def template_address(self, *args) -> Expr:
        """
        template_address returns an expression that will generate the expected
        address given some set of values that should be included in the logic itself
        """
        return Sha512_256(
            Concat(Bytes(PROGRAM_DOMAIN_SEPARATOR), self.populate_template_expr(*args))
        )
