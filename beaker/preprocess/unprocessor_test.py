import pyteal as pt
import ast
from .unprocessor import Unprocessor


def test_unprocessor():
    @pt.Subroutine(pt.TealType.uint64)
    def thing(x):
        return x * x

    prog = pt.Seq(
        pt.Assert(pt.And(pt.Int(1), pt.Int(2))),
        pt.Pop(pt.Int(1)),
        thing(pt.Int(3)),
    )

    prog = pt.Seq(pt.Cond([pt.Int(1), pt.Int(1)], [pt.Int(2), pt.Int(2)]))

    prog = pt.Seq(
        pt.If(pt.Int(1))
        .Then(pt.Int(0))
        .ElseIf(pt.Int(3))
        .Then(pt.Int(2))
        .Else(pt.Int(3))
    )

    print(prog)
    u = Unprocessor(prog)
    print(ast.dump(u.native_ast, indent=4))

    print(ast.unparse(u.native_ast))
