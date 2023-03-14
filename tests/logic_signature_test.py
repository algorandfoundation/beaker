import pyteal as pt
import pytest

from beaker.logic_signature import LogicSignature, LogicSignatureTemplate

from tests.conftest import check_lsig_output_stability


def test_simple_logic_signature() -> None:
    lsig = LogicSignature(pt.Reject())
    assert lsig.program
    check_lsig_output_stability(lsig)


def test_evaluate_logic_signature() -> None:
    lsig = LogicSignature(pt.Approve())
    assert lsig.program
    check_lsig_output_stability(lsig)


def test_handler_logic_signature() -> None:
    def evaluate() -> pt.Expr:
        @pt.Subroutine(pt.TealType.uint64)
        def checked(s: pt.abi.String) -> pt.Expr:
            return pt.Len(s.get()) > pt.Int(0)

        return pt.Seq(
            (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
            pt.Assert(checked(s)),
            pt.Int(1),
        )

    lsig = LogicSignature(evaluate)

    assert lsig.program

    check_lsig_output_stability(lsig)


def test_templated_logic_signature() -> None:
    def evaluate(pubkey: pt.Expr) -> pt.Expr:
        return pt.Seq(
            pt.Assert(pt.Len(pubkey)),
            pt.Int(1),
        )

    lsig = LogicSignatureTemplate(
        evaluate, runtime_template_variables={"pubkey": pt.TealType.bytes}
    )

    assert len(lsig.runtime_template_variables) == 1
    assert lsig.program
    assert "pushbytes TMPL_PUBKEY" in lsig.program

    check_lsig_output_stability(lsig)


def test_different_methods_logic_signature() -> None:
    @pt.ABIReturnSubroutine
    def abi_tester(s: pt.abi.String, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(pt.Len(s.get()))

    @pt.Subroutine(pt.TealType.uint64)
    def internal_tester(x: pt.Expr, y: pt.Expr) -> pt.Expr:
        return x * y

    @pt.Subroutine(pt.TealType.uint64)
    def internal_scratch_tester(x: pt.ScratchVar, y: pt.Expr) -> pt.Expr:
        return x.load() * y

    @pt.ABIReturnSubroutine
    def no_self_abi_tester(x: pt.abi.Uint64, y: pt.abi.Uint64) -> pt.Expr:
        return x.get() * y.get()

    @pt.Subroutine(pt.TealType.uint64)
    def no_self_internal_tester(x: pt.Expr, y: pt.Expr) -> pt.Expr:
        return x * y

    lsig = LogicSignature(
        pt.Seq(
            (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
            (o := pt.abi.Uint64()).set(abi_tester(s)),
            pt.Assert(internal_tester(o.get(), pt.Len(s.get()))),
            (sv := pt.ScratchVar()).store(pt.Int(1)),
            pt.Assert(internal_scratch_tester(sv, o.get())),
            pt.Int(1),
        )
    )

    assert lsig.program

    check_lsig_output_stability(lsig)


def test_lsig_template_ordering() -> None:
    lsig = LogicSignatureTemplate(
        pt.Approve(),
        runtime_template_variables={
            "f": pt.TealType.uint64,
            "a": pt.TealType.uint64,
            "b": pt.TealType.uint64,
            "c": pt.TealType.uint64,
        },
    )
    assert [rtt_var.name for rtt_var in lsig.runtime_template_variables.values()] == [
        "f",
        "a",
        "b",
        "c",
    ]


def test_templated_logic_signature_bad_args() -> None:
    with pytest.raises(ValueError, match="got unexpected arguments: bad_arg.$"):
        LogicSignatureTemplate(
            lambda good_arg, bad_arg: pt.Approve(),
            runtime_template_variables={
                "good_arg": pt.TealType.bytes,
                "missing_arg": pt.TealType.uint64,
            },
        )


def test_templated_logic_signature_no_rtt_vars() -> None:
    with pytest.raises(
        ValueError,
        match="No runtime template variables supplied - use LogicSignature instead if that was intentional",
    ):
        LogicSignatureTemplate(lambda: pt.Approve(), runtime_template_variables={})
