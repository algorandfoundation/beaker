import re
from copy import copy
from algosdk.source_map import SourceMap

from pyteal import PyTealSourceMap

LOGIC_ERROR = "TransactionPool.Remember: transaction ([A-Z0-9]+): logic eval error: (.*). Details: pc=([0-9]+), opcodes=.*"


def parse_logic_error(error_str: str) -> tuple[str, str, int]:
    matches = re.match(LOGIC_ERROR, error_str)
    if matches is None:
        return "", "", 0

    txid = matches.group(1)
    msg = matches.group(2)
    pc = int(matches.group(3))

    return txid, msg, pc


class LogicException(Exception):
    def __init__(
        self,
        logic_error: Exception,
        program: str,
        map: SourceMap,
        pyteal_map: PyTealSourceMap | None,
    ):
        self.logic_error = logic_error
        self.logic_error_str = str(logic_error)

        self.program = program
        self.map = map
        self.lines = program.split("\n")

        self.txid, self.msg, self.pc = parse_logic_error(self.logic_error_str)
        self.line_no = self.map.get_line_for_pc(self.pc)

        self.pyteal_map = pyteal_map

    def __str__(self):
        r = self.pyteal_map.get_r3sourcemap()[self.line_no, 0]
        return (
            f"Txn {self.txid} had error '{self.msg}' at PC {self.pc} and Source Line {self.line_no}."
            f"\nMapped back to PyTeal expression '{r.source_extract}' @ {r.source}::L{r.source_line+1} (COL{r.source_column+1}, COL{r.source_column_end})"
            f"\nSurrounding lines:\n\n\t{self.trace()}"
        )

    def trace(self, lines: int = 5) -> str:
        program_lines = copy(self.lines)
        program_lines[self.line_no] += "\t\t<-- Error"
        lines_before = max(0, self.line_no - lines)
        lines_after = min(len(program_lines), self.line_no + lines)
        return "\n\t".join(program_lines[lines_before:lines_after])
