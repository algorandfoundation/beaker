import base64
from dataclasses import dataclass
from functools import cached_property

from algosdk.constants import APP_PAGE_MAX_SIZE
from algosdk.source_map import SourceMap
from algosdk.v2client.algod import AlgodClient
from pyteal import Bytes, Expr

__all__ = [
    "ProgramAssertion",
    "Program",
]


@dataclass
class ProgramAssertion:
    line: int
    message: str


class Program:
    """
    Precompile takes a TEAL program and handles its compilation. Used by AppPrecompile
    and LSigPrecompile for Applications and Logic Signature programs, respectively.
    """

    def __init__(self, program: str, client: AlgodClient):
        """
        Fully compile the program source to binary and generate a
        source map for matching pc to line number
        """
        self.teal = program
        result = client.compile(self.teal, source_map=True)
        self.raw_binary = base64.b64decode(result["result"])
        self.binary_hash: str = result["hash"]
        self.source_map = SourceMap(result["sourcemap"])

    @cached_property
    def binary(self) -> Bytes:
        return Bytes(self.raw_binary)

    @cached_property
    def assertions(self) -> dict[int, ProgramAssertion]:
        return _gather_asserts(self.teal, self.source_map)

    @cached_property
    def pages(self) -> list[Expr]:
        return [
            Bytes(self.raw_binary[i : i + APP_PAGE_MAX_SIZE])
            for i in range(0, len(self.raw_binary), APP_PAGE_MAX_SIZE)
        ]


def _gather_asserts(program: str, src_map: SourceMap) -> dict[int, ProgramAssertion]:
    asserts: dict[int, ProgramAssertion] = {}

    program_lines = program.split("\n")
    for idx, line in enumerate(program_lines):
        # Take only the first chunk before spaces
        line, *_ = line.split(" ")
        if line != "assert":
            continue

        pcs = src_map.get_pcs_for_line(idx)
        if pcs is None:
            pc = 0
        else:
            pc = pcs[0]

        # TODO: this will be wrong for multiline comments
        line_before = program_lines[idx - 1]
        if not line_before.startswith("//"):
            continue

        asserts[pc] = ProgramAssertion(idx, line_before.strip("/ "))

    return asserts
