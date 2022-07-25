import re

ASSERT_ERROR_PATTERN = "TransactionPool.Remember: transaction ([A-Z0-9]*): logic eval error: assert failed pc=(\d+). Details: pc=(\d+), opcodes=.*"

def parse_logic_error(error_str: str) -> tuple[str, int]:
    matches = re.match(ASSERT_ERROR_PATTERN, error_str)
    txid = matches.group(1)
    pc = int(matches.group(2))
    return txid, pc
