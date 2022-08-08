from typing import Final
from pyteal import abi, Itob, TealType, Subroutine, Concat, Bytes
from beaker.application import Application
from beaker.state import DynamicApplicationStateValue
from beaker.decorators import external


class ARC21(Application):
    """Interface for a round based datafeed oracle"""

    @Subroutine(TealType.bytes)
    def round_key(round):
        return Concat(Bytes("data:"), Itob(round))

    data_for_round: Final[DynamicApplicationStateValue] = DynamicApplicationStateValue(
        stack_type=TealType.bytes, max_keys=64, key_gen=round_key
    )

    @external
    def get(
        self,
        round: abi.Uint64,
        user_data: abi.DynamicArray[abi.Byte],
        *,
        output: abi.DynamicArray[abi.Byte]
    ):
        return output.decode(self.data_for_round[round.get()])

    @external
    def mustGet(
        self,
        round: abi.Uint64,
        user_data: abi.DynamicArray[abi.Byte],
        *,
        output: abi.DynamicArray[abi.Byte]
    ):
        return output.decode(self.data_for_round[round.get()].get_must())
