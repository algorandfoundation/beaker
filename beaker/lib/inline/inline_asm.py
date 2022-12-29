from typing import cast
from pyteal import (
    CompileOptions,
    Expr,
    LeafExpr,
    Mode,
    TealBlock,
    TealType,
    TealOp,
    Op,
    TealSimpleBlock,
)

# Credit Julian (RandLabs)


class CustomOp:
    def __init__(self, opcode: str) -> None:
        self.opcode = opcode
        self.mode = Mode.Signature | Mode.Application
        self.min_version = 2

    def __str__(self) -> str:
        return self.opcode


class InlineAssembly(LeafExpr):
    """InlineAssembly can be used to inject TEAL source directly into a PyTEAL program

    Often the generated PyTEAL is not as efficient as it can be. This class offers a way to
    write the most efficient TEAL for code paths that would otherwise be impossible because
    of opcode budget constraints.

    It can also be used to implement methods that are not yet available in the PyTEAL repository

    Args:
        opcode: string containing the teal to inject
        args: any number of PyTEAL expressions to place before this opcode
        type: The type this Expression returns, to help during PyTEAL compilation

    """

    def __init__(
        self, opcode: str, *args: "Expr", type: TealType = TealType.none
    ) -> None:
        super().__init__()
        opcode_with_args = opcode.split(" ")
        self.op = CustomOp(opcode_with_args[0])
        self.type = type
        self.opcode_args = opcode_with_args[1:]
        self.args = args

    def __teal__(
        self, compile_options: CompileOptions
    ) -> tuple[TealBlock, TealSimpleBlock]:
        op = TealOp(self, cast(Op, self.op), *self.opcode_args)
        return TealBlock.FromOp(compile_options, op, *self.args[::1])

    def __str__(self) -> str:
        return "(InlineAssembly: {})".format(self.op.opcode)

    def type_of(self) -> TealType:
        return self.type
