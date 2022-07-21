from typing import Final, Callable
from pyteal import Int, Expr

# Use these for compile time consts like `payment_amt = Int(10 * algo)`
algo: Final[int] = int(1e6)
milli_algo: Final[int] = int(1e3)

# Use these for runtime algo calculations `Txn.fee()==MilliAlgo`
Algo: Final[Int] = Int(algo)
MilliAlgo: Final[Int] = Int(milli_algo)

# Use this as shorthand for Int(10*algo) like Algos(10)
Algos: Callable[..., Expr] = lambda v: Int(int(v * algo))
MilliAlgos: Callable[..., Expr] = lambda v: Int(int(v * milli_algo))

# aliases for 1/0
TRUE: Final[Int] = Int(1)
FALSE: Final[Int] = Int(0)

# TODO: find consts
MAX_LOCAL_STATE = 16
MAX_GLOBAL_STATE = 64

# TODO: replace with pysdk when its released
APP_MAX_PAGE_SIZE = 2048
