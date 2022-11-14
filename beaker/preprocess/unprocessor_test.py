import pytest
import pyteal as pt
import ast
from .unprocessor import Unprocessor


def get_subroutine_test():
    @pt.Subroutine(pt.TealType.uint64)
    def thing(x):
        return x * x

    return (
        pt.Seq(
            pt.Assert(pt.And(pt.Int(1), pt.Int(2))),
            pt.Pop(pt.Int(1)),
            thing(pt.Int(3)),
        ),
        """
assert 1 and 2

_ = 1
thing(3)""",
    )


TRANSLATE_TESTS: list[tuple[pt.Expr, str]] = [
    (
        pt.Seq(pt.Cond([pt.Int(1), pt.Int(1)], [pt.Int(2), pt.Int(2)])),
        """\nif 1:\n    1\nelif 2:\n    2""",
    ),
    (
        pt.Seq(pt.Assert(pt.Len(pt.Txn.sender()) > pt.Int(0)), pt.Int(1)),
        """\nassert len(txn_sender()) > 0\n1""",
    ),
    # (
    #    pt.Seq(
    #        pt.If(pt.Int(1))
    #        .Then(pt.Int(0))
    #        .ElseIf(pt.Int(3))
    #        .Then(pt.Int(2))
    #        .Else(pt.Int(3))
    #    ),
    #    """\nif 1:\n\t0\nelif 3:\n\t2\nelse:3""",  # TODO: need to make this appear on its own line?
    # ),
    # (
    #    pt.Seq((x := pt.ScratchVar()).store(pt.Int(1)), x.load()),
    #    """\nvar_256 = 1\nvar_256""",
    # ),
    # get_subroutine_test(),
]


@pytest.mark.parametrize("ptexpr,pystr", TRANSLATE_TESTS)
def test_unprocessor(ptexpr: pt.Expr, pystr: str):

    u = Unprocessor(ptexpr)
    print(ast.dump(u.native_ast, indent=4))

    actual_str = ast.unparse(u.native_ast)
    assert actual_str == pystr


def test_amm():
    from .amm import ConstantProductAMM
    from typing import cast

    cpamm = ConstantProductAMM()
    approval, _, _ = cpamm.router.build_program()
    up = Unprocessor(approval)
    # print(ast.dump(up.native_ast, indent=4))
    print()
    print(ast.unparse(up.native_ast))
