import re
from copy import copy
from typing import TypedDict

from algosdk.source_map import SourceMap

LOGIC_ERROR = "TransactionPool.Remember: transaction (?P<txid>[A-Z0-9]+): logic eval error: (?P<msg>.*). Details: pc=(?P<pc>[0-9]+), opcodes=.*"


class LogicErrorData(TypedDict):
    txid: str
    msg: str
    pc: int


def parse_logic_error(
    error_str: str,
) -> LogicErrorData | None:
    match = re.match(LOGIC_ERROR, error_str)
    if match is None:
        return None

    return {
        "txid": match.group("txid"),
        "msg": match.group("msg"),
        "pc": int(match.group("pc")),
    }


class LogicException(Exception):
    def __init__(
        self,
        logic_error: Exception,
        program: str,
        map: SourceMap,
        txid: str,
        msg: str,
        pc: int,
    ):
        self.logic_error = logic_error
        self.logic_error_str = str(logic_error)

        self.program = program
        self.map = map
        self.lines = program.split("\n")

        self.txid, self.msg, self.pc = txid, msg, pc
        line = self.map.get_line_for_pc(self.pc)
        self.line_no = line if line is not None else 0

    def __str__(self) -> str:
        return f"Txn {self.txid} had error '{self.msg}' at PC {self.pc} and Source Line {self.line_no}: \n\n\t{self.trace()}"

    def trace(self, lines: int = 5) -> str:
        program_lines = copy(self.lines)
        program_lines[self.line_no] += "\t\t<-- Error"
        lines_before = max(0, self.line_no - lines)
        lines_after = min(len(program_lines), self.line_no + lines)
        return "\n\t".join(program_lines[lines_before:lines_after])
