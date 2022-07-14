from typing import Final
from pyteal import Int

# Use these for compile time consts like `payment_amt = Int(10 * algo)`
algo: Final[int] = int(1e6)
milli_algo: Final[int] = int(1e3)

# Use these for runtime algo calculations `Txn.fee()==MilliAlgo`
Algo: Final[Int] = Int(algo)
MilliAlgo: Final[Int] = Int(milli_algo)

# aliases for 1/0
TRUE: Final[Int] = Int(1)
FALSE: Final[Int] = Int(0)
