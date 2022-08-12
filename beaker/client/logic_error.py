import re
from algosdk.source_map import SourceMap

LOGIC_ERROR = "TransactionPool.Remember: transaction ([A-Z0-9]+): logic eval error: (.*). Details: pc=([0-9]+), opcodes=.*"


def parse_logic_error(error_str: str) -> tuple[str, str, int]:
    matches = re.match(LOGIC_ERROR, error_str)
    if matches is None:
        return "", "", 0

    txid = matches.group(1)
    msg = matches.group(2)
    pc = int(matches.group(3))

    return txid, msg, pc


def tiny_trace(program: str, line_no: int, num_lines: int) -> str:
    lines = program.split("\n")
    lines[line_no] += "\t\t<-- Error"
    lines_before = max(0, line_no - num_lines)
    lines_after = min(len(lines), line_no + num_lines)
    return "\n\t".join(lines[lines_before:lines_after])


class LogicException(Exception):
    def __init__(
        self,
        logic_error: Exception,
        program: str,
        map: SourceMap,
    ):
        self.logic_error = logic_error
        self.logic_error_str = str(logic_error)

        self.program = program
        self.map = map

        self.txid, self.msg, self.pc = parse_logic_error(self.logic_error_str)
        self.line_no = self.map.get_line_for_pc(self.pc)

    def __str__(self):
        return f"Txn {self.txid} had error '{self.msg}' at PC {self.pc} and Source Line {self.line_no}: \n\n\t{self.trace()}"

    def trace(self, lines: int = 5) -> str:
        return tiny_trace(self.program, self.line_no, lines)
