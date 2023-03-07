from collections.abc import KeysView
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pyteal import (
    Addr,
    Bytes,
    Concat,
    Expr,
    Int,
    Len,
    ScratchVar,
    Seq,
    Sha512_256,
    Substring,
    Suffix,
    TealType,
    TealTypeError,
    TxnField,
    TxnType,
)
from pyteal.types import require_type

from beaker.compilation import Program
from beaker.consts import PROGRAM_DOMAIN_SEPARATOR, num_extra_program_pages
from beaker.lib.strings import EncodeUVarInt

if TYPE_CHECKING:
    from algosdk.v2client.algod import AlgodClient

    from beaker.application import Application
    from beaker.logic_signature import (
        LogicSignature,
        LogicSignatureTemplate,
    )


__all__ = [
    "PrecompiledApplication",
    "PrecompiledLogicSignature",
    "PrecompiledLogicSignatureTemplate",
    "PrecompileContextError",
]


class PrecompiledApplication:
    """
    AppPrecompile allows a smart contract to signal that some child Application
    should be fully compiled prior to constructing its own program.
    """

    def __init__(self, app: "Application", client: "AlgodClient"):
        app_spec = app.build(client)
        self._global_schema = app_spec.global_state_schema
        self._local_schema = app_spec.local_state_schema

        # at this point, we should have all the dependant logic built
        # so we can compile the app teal
        self.approval_program = Program(app_spec.approval_program, client)
        self.clear_program = Program(app_spec.clear_program, client)

    def get_create_config(self) -> dict[TxnField, Expr | list[Expr]]:
        """get a dictionary of the fields and values that should be set when
        creating this application that can be passed directly to
        the InnerTxnBuilder.Execute method
        """
        result: dict[TxnField, Expr | list[Expr]] = {
            TxnField.type_enum: TxnType.ApplicationCall,
        }
        extra_pages = num_extra_program_pages(
            self.approval_program.raw_binary, self.clear_program.raw_binary
        )
        approval_pages = self.approval_program.pages
        clear_pages = self.clear_program.pages
        if extra_pages == 0:
            assert len(approval_pages) == 1
            assert len(clear_pages) == 1
            result[TxnField.approval_program] = approval_pages[0]
            result[TxnField.clear_state_program] = clear_pages[0]
        else:
            result[TxnField.approval_program_pages] = approval_pages
            result[TxnField.clear_state_program_pages] = clear_pages
            result[TxnField.extra_program_pages] = Int(extra_pages)

        if l_nbs := self._local_schema.num_byte_slices:
            result[TxnField.local_num_byte_slices] = Int(l_nbs)
        if l_nui := self._local_schema.num_uints:
            result[TxnField.local_num_uints] = Int(l_nui)
        if g_nbs := self._global_schema.num_byte_slices:
            result[TxnField.global_num_byte_slices] = Int(g_nbs)
        if g_nui := self._global_schema.num_uints:
            result[TxnField.global_num_uints] = Int(g_nui)
        return result


class PrecompiledLogicSignature:
    """
    LSigPrecompile allows a smart contract to signal that some child Logic Signature
    should be fully compiled prior to constructing its own program.
    """

    def __init__(self, lsig: "LogicSignature", client: "AlgodClient"):
        self.logic_program = Program(lsig.program, client)

    def address(self) -> Expr:
        """Get the address from this LSig program."""
        return Addr(self.logic_program.binary_hash)


@dataclass
class PrecompileTemplateValue:
    #: Whether or not this variable is bytes (if false, its uint64)
    is_bytes: bool = field(kw_only=True)
    #: The line number in the source TEAL this variable is present
    line: int = field(kw_only=True)
    #: The pc of the variable in the assembled bytecode
    pc: int = 0


class PrecompiledLogicSignatureTemplate:
    """
    LSigPrecompile allows a smart contract to signal that some child Logic Signature
    should be fully compiled prior to constructing its own program.
    """

    def __init__(self, lsig: "LogicSignatureTemplate", client: "AlgodClient"):
        self._template_values: dict[str, PrecompileTemplateValue] = {}

        lines = lsig.program.splitlines()
        # Replace the teal program TMPL_* template variables with
        # the 0 value for the given type and save the list of TemplateValues
        for rtt_var in lsig.runtime_template_variables.values():
            token = rtt_var.token
            is_bytes = rtt_var.type_of() == TealType.bytes
            op = "pushbytes" if is_bytes else "pushint"
            statement = f"{op} {token} // {token}"
            idx = lines.index(statement)
            lines[idx] = lines[idx].replace(token, '""' if is_bytes else "0", 1)
            self._template_values[rtt_var.name] = PrecompileTemplateValue(
                is_bytes=is_bytes, line=idx
            )

        self.logic_program = Program("\n".join(lines), client)

        for tv in self._template_values.values():
            # +1 to acount for the pushbytes/pushint op
            pcs = self.logic_program.source_map.get_pcs_for_line(tv.line)
            if pcs is None:
                tv.pc = 0
            else:
                tv.pc = pcs[0] + 1

    def address(self, **kwargs: Expr) -> Expr:
        """
        returns an expression that will generate the expected
        hash given some set of values that should be included in the logic itself
        """
        self._check_kwargs(kwargs.keys())

        return Sha512_256(
            Concat(
                Bytes(PROGRAM_DOMAIN_SEPARATOR),
                self.populate_template_expr(**kwargs),
            )
        )

    def _check_kwargs(self, keys: KeysView[str]) -> None:
        if keys != self._template_values.keys():
            raise ValueError(
                f"Expected arguments named: {', '.join(self._template_values.keys())} "
                f"but got: {', '.join(keys)}"
            )

    def populate_template_expr(self, **kwargs: Expr) -> Expr:
        """
        populate_template_expr returns the Expr that will patch a
        blank binary given a set of arguments.

        It is called by ``address`` to return an Expr that
        can be used to compare with a sender given some arguments.
        """

        # To understand how this works, first look at the pure python one above
        # it should produce an identical output in terms of populated binary.
        # This function just reproduces the same effects in pyteal

        self._check_kwargs(kwargs.keys())

        populate_program: list[Expr] = [
            (last_pos := ScratchVar(TealType.uint64)).store(Int(0)),
            (offset := ScratchVar(TealType.uint64)).store(Int(0)),
            (curr_val := ScratchVar(TealType.bytes)).store(Bytes("")),
            (buff := ScratchVar(TealType.bytes)).store(Bytes("")),
        ]

        for name, tv in self._template_values.items():
            # Add expressions to encode the values and insert
            # them into the working buffer
            arg = kwargs[name]
            require_type(arg, TealType.bytes if tv.is_bytes else TealType.uint64)
            populate_program += [
                curr_val.store(Concat(EncodeUVarInt(Len(arg)), arg))
                if tv.is_bytes
                else curr_val.store(EncodeUVarInt(arg)),
                buff.store(
                    Concat(
                        buff.load(),
                        Substring(
                            self.logic_program.binary,
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
            buff.store(
                Concat(buff.load(), Suffix(self.logic_program.binary, last_pos.load()))
            ),
            buff.load(),
        ]

        return Seq(*populate_program)

    def populate_template(self, **kwargs: str | bytes | int) -> bytes:
        """
        populate_template returns the bytes resulting from patching the set of
        arguments passed into the blank binary

        The args passed should be of the same type and in the same order as the
        template values declared.
        """

        self._check_kwargs(kwargs.keys())

        # Get a copy of the binary so we can work on it in place
        populated_binary = list(self.logic_program.raw_binary)
        # Any time we add bytes, we need to update the offset so the rest
        # of the pc values can be updated to account for the difference
        offset = 0
        for name, tv in self._template_values.items():
            arg = kwargs[name]

            if tv.is_bytes:
                if type(arg) is int:
                    raise TealTypeError(type(arg), bytes | str)

                if type(arg) is str:
                    arg = arg.encode("utf-8")

                assert type(arg) is bytes

                # Bytes are encoded as uvarint(len(bytes)) + bytes
                curr_val = _py_encode_uvarint(len(arg)) + arg
            else:
                if type(arg) is not int:
                    raise TealTypeError(type(arg), int)
                # Ints are just the uvarint encoded number
                curr_val = _py_encode_uvarint(arg)

            # update the working buffer to include the new value,
            # replacing the current 0 value
            populated_binary[tv.pc + offset : tv.pc + offset + 1] = curr_val

            # update the offset with the length(value) - 1 to account
            # for the existing 0 value and help keep track of how to shift the pc later
            offset += len(curr_val) - 1

        return bytes(populated_binary)


class PrecompileContextError(Exception):
    pass


def _py_encode_uvarint(integer: int) -> bytes:
    """Encodes an integer as an uvarint.
    :param integer: the integer to encode
    :return: bytes containing the integer encoded as an uvarint
    """

    def to_byte(x: int) -> int:
        return x & 0b1111_1111

    buffer: bytearray = bytearray()

    while integer >= 0b1000_0000:
        buffer.append(to_byte(integer) | 0b1000_0000)
        integer >>= 7

    buffer.append(to_byte(integer))

    return bytes(buffer)
