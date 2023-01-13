import pyteal as pt
from beaker.logic_signature import LogicSignature


def test_simple_logic_signature():
    lsig = LogicSignature(evaluate=pt.Reject())
    assert lsig.program


def test_evaluate_logic_signature():
    lsig = LogicSignature(evaluate=pt.Approve())
    assert lsig.program


def test_handler_logic_signature():
    def evaluate():
        @pt.Subroutine(pt.TealType.uint64)
        def checked(s: pt.abi.String):
            return pt.Len(s.get()) > pt.Int(0)

        return pt.Seq(
            (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
            pt.Assert(checked(s)),
            pt.Int(1),
        )

    def Lsig():
        return LogicSignature(evaluate)

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.program) > 0


def test_templated_logic_signature():
    def Lsig() -> LogicSignature:
        def evaluate(pubkey: pt.Expr):
            return pt.Seq(
                pt.Assert(pt.Len(pubkey)),
                pt.Int(1),
            )

        return LogicSignature(
            evaluate, runtime_template_variables={"pubkey": pt.TealType.bytes}
        )

    lsig = Lsig()

    assert len(lsig.template_variables) == 1
    assert len(lsig.program) > 0

    assert "pushbytes TMPL_PUBKEY" in lsig.program


def test_different_methods_logic_signature():
    @pt.ABIReturnSubroutine
    def abi_tester(s: pt.abi.String, *, output: pt.abi.Uint64):
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

    def Lsig() -> LogicSignature:
        def evaluate():
            return pt.Seq(
                (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
                (o := pt.abi.Uint64()).set(abi_tester(s)),
                pt.Assert(internal_tester(o.get(), pt.Len(s.get()))),
                (sv := pt.ScratchVar()).store(pt.Int(1)),
                pt.Assert(internal_scratch_tester(sv, o.get())),
                pt.Int(1),
            )

        return LogicSignature(evaluate)

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.program) > 0


def test_lsig_template_ordering():
    def Lsig() -> LogicSignature:
        return LogicSignature(
            pt.Approve(),
            runtime_template_variables={
                "f": pt.TealType.uint64,
                "a": pt.TealType.uint64,
                "b": pt.TealType.uint64,
                "c": pt.TealType.uint64,
            },
        )

    expected = ["f", "a", "b", "c"]

    l = Lsig()
    for idx, tv in enumerate(l.template_variables):
        assert tv.name == expected[idx]
