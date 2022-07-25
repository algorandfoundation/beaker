import re
from algosdk.source_map import SourceMap
from beaker import Application

ASSERT_ERROR_PATTERN = "TransactionPool.Remember: transaction ([A-Z0-9]+): logic eval error: assert failed pc=([0-9]+). Details: pc=([0-9]+), opcodes=.*"


def parse_logic_error(error_str: str) -> tuple[str, int]:
    matches = re.match(ASSERT_ERROR_PATTERN, error_str)
    txid = matches.group(1)
    pc = int(matches.group(2))
    return txid, pc


def tiny_trace(approval_program: str, line_no: int, lines: int) -> str:
    approval_lines = approval_program.split("\n")
    approval_lines[line_no] += "\t\t<-- Error"
    lines_before = max(0, line_no - lines)
    lines_after = min(len(approval_lines), line_no + lines)
    return "\n\t".join(approval_lines[lines_before:lines_after])


class LogicException(Exception):
    def __init__(
        self,
        logic_error: Exception,
        app: Application,
        approval_map: SourceMap,
        clear_map: SourceMap,
    ):
        self.logic_error = logic_error
        self.logic_error_str = str(logic_error)
        self.app = app
        self.approval_map = approval_map
        self.clear_map = clear_map
        # TODO: check if it was the clear or approval program
        self.txid, self.pc = parse_logic_error(self.logic_error_str)

    def __str__(self):
        line_no = self.approval_map.get_line_for_pc(self.pc)
        trace = tiny_trace(self.app.approval_program, line_no, 5)
        return f"Txn({self.txid}) had logic error at pc {self.pc} and source line {line_no}: \n\n\t{trace}"
