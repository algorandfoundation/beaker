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


# @pytest.mark.parametrize("ptexpr,pystr", TRANSLATE_TESTS)
# def test_unprocessor(ptexpr: pt.Expr, pystr: str):
#
#    u = Unprocessor(ptexpr)
#    print(ast.dump(u.native_ast, indent=4))
#
#    actual_str = ast.unparse(u.native_ast)
#    assert actual_str == pystr


def test_amm():
    from .amm import ConstantProductAMM

    cpamm = ConstantProductAMM()
    approval, _, _ = cpamm.router.build_program()
    methods = {k: v[0].subroutine for k, v in cpamm.methods.items()}
    up = Unprocessor(approval, name="main", methods=methods)
    print()
    print(ast.unparse(up.native_ast))

    for k, (meth, _) in cpamm.methods.items():
        subr = meth.subroutine
        if subr.has_abi_output:
            continue

        kwargs = {}
        for a, v in subr.abi_args.items():
            kwargs[a] = v.new_instance()

        subr_call = meth.subroutine.implementation(**kwargs)
        mup = Unprocessor(subr_call, name=k, methods=methods)
        print(ast.unparse(mup.native_ast))

    # {
    #   'id': 41,
    #   'return_type': <TealType.none: 3>,
    #   'declaration': None,
    #   'declarations': <pyteal._SubroutineDeclByVersion object at 0x7f05a5312830>,
    #   'implementation': <bound method ConstantProductAMM.swap of <beaker.preprocess.amm.ConstantProductAMM object at 0x7f05a543b6a0>>,
    #   'has_abi_output': False,
    #   'implementation_params': mappingproxy(OrderedDict([
    #         ('swap_xfer', <Parameter "swap_xfer: pyteal.abi.AssetTransferTransaction">),
    #         ('a_asset', <Parameter "a_asset: pyteal.abi.Asset">),
    #         ('b_asset', <Parameter "b_asset: pyteal.abi.Asset">)
    #   ])),
    #   'annotations': {
    #         'swap_xfer': <class 'pyteal.abi.AssetTransferTransaction'>,
    #         'a_asset': <class 'pyteal.abi.Asset'>,
    #         'b_asset': <class 'pyteal.abi.Asset'>
    #   },
    #   'expected_arg_types': [
    #         <pyteal.abi.AssetTransferTransactionTypeSpec object at 0x7f05a5312a70>,
    #         <pyteal.abi.AssetTypeSpec object at 0x7f05a5312a40>,
    #         <pyteal.abi.AssetTypeSpec object at 0x7f05a5312aa0>
    #   ],
    #   'by_ref_args': set(),
    #   'abi_args': {
    #       'swap_xfer': <pyteal.abi.AssetTransferTransactionTypeSpec object at 0x7f05a5312a70>,
    #       'a_asset': <pyteal.abi.AssetTypeSpec object at 0x7f05a5312a40>,
    #       'b_asset': <pyteal.abi.AssetTypeSpec object at 0x7f05a5312aa0>
    #    },
    #   'output_kwarg': {},
    #   '_SubroutineDefinition__name': 'swap',
    #   'locals_suggested': None
    # }
