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
        """
if 1:
    1
elif 2:
    2""",
    ),
    (
        pt.Seq(pt.Assert(pt.Len(pt.Txn.sender()) > pt.Int(0)), pt.Int(1)),
        """
assert len(txn_sender()) > 0
1""",
    ),
    (
        pt.Seq(
            pt.If(pt.Int(1))
            .Then(pt.Int(0))
            .ElseIf(pt.Int(3))
            .Then(pt.Int(2))
            .Else(pt.Int(3))
        ),
        """
if 1:
    0
elif 3:
    2
else:3""",  # TODO: need to make this appear on its own line?
    ),
    (
        pt.Seq((x := pt.ScratchVar()).store(pt.Int(1)), x.load()),
        """
var_256 = 1
var_256""",
    ),
    get_subroutine_test(),
]


@pytest.mark.parametrize("ptexpr,pystr", TRANSLATE_TESTS)
def test_unprocessor(ptexpr: pt.Expr, pystr: str):

    u = Unprocessor(ptexpr)
    print(ast.dump(u.native_ast, indent=4))

    actual_str = ast.unparse(u.native_ast)
    assert actual_str == pystr
