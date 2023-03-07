import base64
from functools import cached_property

from algosdk.constants import APP_PAGE_MAX_SIZE
from algosdk.source_map import SourceMap
from algosdk.v2client.algod import AlgodClient
from pyteal import Bytes, Expr

__all__ = [
    "Program",
]


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
        self._result = client.compile(self.teal, source_map=True)
        self.raw_binary = base64.b64decode(self._result["result"])
        self.binary_hash: str = self._result["hash"]
        self.source_map = SourceMap(self._result["sourcemap"])

    @cached_property
    def binary(self) -> Bytes:
        return Bytes(self.raw_binary)

    @cached_property
    def pages(self) -> list[Expr]:
        return [
            Bytes(self.raw_binary[i : i + APP_PAGE_MAX_SIZE])
            for i in range(0, len(self.raw_binary), APP_PAGE_MAX_SIZE)
        ]
