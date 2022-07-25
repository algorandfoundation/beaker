from typing import Final, Callable
from pyteal import Int, Expr

#: Used these for compile time consts like `payment_amt = Int(10 * algo)`
#: number of microalgos in 1 Algo
algo: Final[int] = int(1e6)
#: number of microalgos in 1 MilliAlgo
milli_algo: Final[int] = int(1e3)

#: Used for runtime algo calculations `Txn.fee()==MilliAlgo`
Algo: Final[Int] = Int(algo)
MilliAlgo: Final[Int] = Int(milli_algo)

#: Used for shorthand for Int(10*algo) like Algos(10)
Algos: Callable[..., Expr] = lambda v: Int(int(v * algo))
MilliAlgos: Callable[..., Expr] = lambda v: Int(int(v * milli_algo))

#: Max number of inner transactions that may be called
MAX_INNERS = 255
#: Single app call opcode budget
APP_CALL_BUDGET = 700
#: Max possible opcode budget
MAX_OPS = MAX_INNERS * APP_CALL_BUDGET

AppCallBudget = Int(APP_CALL_BUDGET)
MaxOps = Int(MAX_OPS)


# aliases for 1/0
TRUE: Final[Int] = Int(1)
FALSE: Final[Int] = Int(0)

# TODO: find consts
MAX_LOCAL_STATE = 16
MAX_GLOBAL_STATE = 64

# TODO: replace with pysdk when its released
APP_MAX_PAGE_SIZE = 2048
