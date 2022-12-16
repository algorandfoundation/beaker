import base64
from Cryptodome.Hash import SHA512
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from pyteal import (
    Seq,
    Bytes,
    Expr,
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
    TxnField,
    TxnType,
)
from algosdk.v2client.algod import AlgodClient
from algosdk.source_map import SourceMap
from algosdk.future.transaction import LogicSigAccount
from algosdk.constants import APP_PAGE_MAX_SIZE
from algosdk.atomic_transaction_composer import LogicSigTransactionSigner
from beaker.consts import PROGRAM_DOMAIN_SEPARATOR, num_extra_program_pages
from beaker.lib.strings import encode_uvarint

if TYPE_CHECKING:
    from beaker.application import Application
    from beaker.logic_signature import LogicSignature


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


@dataclass
class ProgramPage:
    #: index of the program page
    index: int = field(kw_only=True, init=True)
    #: binary of the page
    _binary: bytes = field(kw_only=True, init=True)
    #: bytes of the page as pyteal Bytes
    binary: Bytes = field(init=False)
    #: hash of the page in native bytes
    _hash_digest: bytes = field(kw_only=True, init=True)
    #: hash of the page as pyteal Addr
    hash_digest: Bytes = field(init=False)

    def __post_init__(self) -> None:
        self.binary = Bytes(self._binary)
        self.hash_digest = Bytes(self._hash_digest)


class Precompile:
    """
    Precompile takes a TEAL program and handles its compilation. Used by AppPrecompile
    and LSigPrecompile for Applications and Logic Signature programs, respectively.
    """

    _program: str = ""
    _binary: Optional[bytes] = None
    _program_hash: Optional[str] = None
    _map: Optional[SourceMap] = None
    _template_values: list[PrecompileTemplateValue] = []
    program_pages: list[ProgramPage]
    binary: Bytes = Bytes("")

    def __init__(self, program: str):
        self._program = program
        lines = self._program.splitlines()
        template_values: list[PrecompileTemplateValue] = []
        # Replace the teal program TMPL_* template variables with
        # the 0 value for the given type and save the list of TemplateValues
        for idx, line in enumerate(lines):
            if TMPL_PREFIX in line:
                op, name, _, _ = line.split(" ")
                tv = PrecompileTemplateValue(
                    name=name[len(TMPL_PREFIX) :], is_bytes=op == PUSH_BYTES, line=idx
                )
                lines[idx] = line.replace(name, ZERO_BYTES if tv.is_bytes else ZERO_INT)
                template_values.append(tv)

        program = "\n".join(lines)

        self._program = program
        self._template_values = template_values

    def assemble(self, client: AlgodClient) -> None:
        """
        Fully compile the program source to binary and generate a
        source map for matching pc to line number
        """
        result = client.compile(self._program, source_map=True)
        self._binary = base64.b64decode(result["result"])
        self._program_hash = result["hash"]

        self._map = SourceMap(result["sourcemap"])

        self._asserts = _gather_asserts(self._program, self._map)

        self.binary = Bytes(self._binary)
        for tv in self._template_values:
            # +1 to acount for the pushbytes/pushint op
            tv.pc = self._map.get_pcs_for_line(tv.line)[0] + 1

        def _hash_program(data: bytes) -> bytes:
            """compute the hash"""
            chksum = SHA512.new(truncate="256")
            chksum.update(PROGRAM_DOMAIN_SEPARATOR.encode() + data)
            return chksum.digest()

        self.program_pages = [
            ProgramPage(
                index=i,
                _binary=self._binary[i : i + APP_PAGE_MAX_SIZE],
                _hash_digest=_hash_program(self._binary[i : i + APP_PAGE_MAX_SIZE]),
            )
            for i in range(0, len(self._binary), APP_PAGE_MAX_SIZE)
        ]

    def hash(self, page_idx: int = 0) -> Expr:
        """hash returns an expression for this Precompile.
                It will fail if any template_values are set.

        Args:
            page_idx(optional): If the application has multiple pages,
            the index of the page can be specified to get the program hash
            for that page.

        """
        assert self._binary is not None
        assert len(self._template_values) == 0
        if self._program_hash is None:
            raise TealInputError("No address defined for precompile")

        return self.program_pages[page_idx].hash_digest

    def populate_template(self, *args: str | bytes | int) -> bytes:
        """
        populate_template returns the bytes resulting from patching the set of
        arguments passed into the blank binary

        The args passed should be of the same type and in the same order as the
        template values declared.
        """

        assert self._binary is not None
        assert len(self._template_values) > 0
        assert len(args) == len(self._template_values)

        # Get a copy of the binary so we can work on it in place
        populated_binary = list(self._binary).copy()
        # Any time we add bytes, we need to update the offset so the rest
        # of the pc values can be updated to account for the difference
        offset = 0
        for idx, tv in enumerate(self._template_values):
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

            # update the working buffer to include the new value,
            # replacing the current 0 value
            populated_binary[tv.pc + offset : tv.pc + offset + 1] = curr_val

            # update the offset with the length(value) - 1 to account
            # for the existing 0 value and help keep track of how to shift the pc later
            offset += len(curr_val) - 1

        return bytes(populated_binary)

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

        assert self.binary is not None
        assert len(self._template_values)
        assert len(args) == len(self._template_values)

        populate_program: list[Expr] = [
            (last_pos := ScratchVar(TealType.uint64)).store(Int(0)),
            (offset := ScratchVar(TealType.uint64)).store(Int(0)),
            (curr_val := ScratchVar(TealType.bytes)).store(Bytes("")),
            (buff := ScratchVar(TealType.bytes)).store(Bytes("")),
        ]

        for idx, tv in enumerate(self._template_values):
            # Add expressions to encode the values and insert
            # them into the working buffer
            populate_program += [
                curr_val.store(Concat(encode_uvarint(Len(args[idx])), args[idx]))
                if tv.is_bytes
                else curr_val.store(encode_uvarint(args[idx])),
                buff.store(
                    Concat(
                        buff.load(),
                        Substring(
                            self.binary,
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
            buff.store(Concat(buff.load(), Suffix(self.binary, last_pos.load()))),
            buff.load(),
        ]

        @Subroutine(TealType.bytes)
        def populate_template_program() -> Expr:
            return Seq(*populate_program)

        return populate_template_program()

    def template_hash(self, *args) -> Expr:  # type: ignore
        """
        returns an expression that will generate the expected
        hash given some set of values that should be included in the logic itself
        """
        return Sha512_256(
            Concat(Bytes(PROGRAM_DOMAIN_SEPARATOR), self.populate_template_expr(*args))
        )


class AppPrecompile:
    """
    AppPrecompile allows a smart contract to signal that some child Application
    should be fully compiled prior to constructing its own program.
    """

    def __init__(self, app: "Application"):
        #: The App to be used and compiled before it's parent
        self.app: "Application" = app
        #: The App's approval program as a Precompile
        self.approval: Precompile = Precompile("")
        #: The App's clear program as a Precompile
        self.clear: Precompile = Precompile("")

    def compile(self, client: AlgodClient) -> None:
        """fully compile this app precompile by recursively
            compiling children depth first

        Note:
            Must be called (even indirectly) prior to using
                the ``approval`` and ``clear`` fields
        """
        for p in self.app.precompiles.values():
            p.compile(client)

        # at this point, we should have all the dependant logic built
        # so we can compile the app teal
        approval, clear = self.app.compile(client)
        self.approval = Precompile(approval)
        self.clear = Precompile(clear)
        if self.approval._binary is None:
            self.approval.assemble(client)
        if self.clear._binary is None:
            self.clear.assemble(client)

    def get_create_config(self) -> dict[TxnField, Expr | list[Expr]]:
        """get a dictionary of the fields and values that should be set when
        creating this application that can be passed directly to
        the InnerTxnBuilder.Execute method
        """
        assert self.approval._binary is not None
        assert self.clear._binary is not None
        return {
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.local_num_byte_slices: Int(self.app.acct_state.num_byte_slices),
            TxnField.local_num_uints: Int(self.app.acct_state.num_uints),
            TxnField.global_num_byte_slices: Int(self.app.app_state.num_byte_slices),
            TxnField.global_num_uints: Int(self.app.app_state.num_uints),
            TxnField.approval_program_pages: [
                page.binary for page in self.approval.program_pages
            ],
            TxnField.clear_state_program_pages: [
                page.binary for page in self.clear.program_pages
            ],
            TxnField.extra_program_pages: Int(
                num_extra_program_pages(self.approval._binary, self.clear._binary)
            ),
        }


class LSigPrecompile:
    """
    LSigPrecompile allows a smart contract to signal that some child Logic Signature
    should be fully compiled prior to constructing its own program.
    """

    def __init__(self, lsig: "LogicSignature"):
        #: the LogicSignature to be used and compiled before it's parent
        self.lsig: "LogicSignature" = lsig

        #: The LogicSignature's logic as a Precompile
        self.logic: Precompile = Precompile("")

    def compile(self, client: AlgodClient) -> None:
        """
        fully compile this lsig precompile by recursively compiling children depth first

        Note:
            Must be called (even indirectly) prior to using the ``logic`` field
        """
        for p in self.lsig.precompiles.values():
            p.compile(client)

        # at this point, we should have all the dependant logic built
        # so we can compile the lsig teal
        self.logic = Precompile(self.lsig.compile(client))

        if self.logic._binary is None:
            self.logic.assemble(client)

    def template_signer(self, *args: str | bytes | int) -> LogicSigTransactionSigner:
        """Get the Signer object for a populated version of the template contract"""
        return LogicSigTransactionSigner(
            LogicSigAccount(self.logic.populate_template(*args))
        )

    def signer(self) -> LogicSigTransactionSigner:
        """
        signer returns a LogicSigTransactionSigner to be used with
        an ApplicationClient or AtomicTransactionComposer.

        It should only be used for non templated Precompiles.
        """
        return LogicSigTransactionSigner(LogicSigAccount(self.logic._binary))


@dataclass
class ProgramAssertion:
    line: int
    message: str


def _gather_asserts(program: str, src_map: SourceMap) -> dict[int, ProgramAssertion]:
    asserts: dict[int, ProgramAssertion] = {}

    program_lines = program.split("\n")
    for idx, line in enumerate(program_lines):
        # Take only the first chunk before spaces
        line = line.split(" ").pop()
        if line != "assert":
            continue

        pc = src_map.get_pcs_for_line(idx)[0]

        # TODO: this will be wrong for multiline comments
        line_before = program_lines[idx - 1]
        if not line_before.startswith("//"):
            continue

        asserts[pc] = ProgramAssertion(idx, line_before.strip("// "))

    return asserts


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
