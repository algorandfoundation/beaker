import pytest
import pyteal as pt
from beaker.decorators import internal
from beaker.logic_signature import LogicSignature, TemplateVariable


def test_simple_logic_signature():
    class Lsig(LogicSignature):
        pass

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.methods) == 0
    assert len(lsig.attrs.keys()) == 1
    assert len(lsig.program) > 0

    assert "evaluate" in lsig.attrs

    assert lsig.evaluate() == pt.Reject()

    # Cant call it from static context
    with pytest.raises(TypeError):
        Lsig.evaluate()


def test_evaluate_logic_signature():
    class Lsig(LogicSignature):
        def evaluate(self):
            return pt.Approve()

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.methods) == 0
    assert len(lsig.attrs.keys()) == 1
    assert len(lsig.program) > 0

    assert "evaluate" in lsig.attrs

    assert lsig.evaluate() == pt.Approve()

    # Cant call it from static context
    with pytest.raises(TypeError):
        Lsig.evaluate()


def test_handler_logic_signature():
    class Lsig(LogicSignature):
        def evaluate(self):
            return pt.Seq(
                (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
                pt.Assert(self.checked(s)),
                pt.Int(1),
            )

        @internal(pt.TealType.uint64)
        def checked(self, s: pt.abi.String):
            return pt.Len(s.get()) > pt.Int(0)

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.methods) == 0
    assert len(lsig.attrs.keys()) == 2
    assert len(lsig.program) > 0

    assert "evaluate" in lsig.attrs

    # Should not fail
    lsig.evaluate()
    lsig.checked(pt.abi.String())

    # Cant call it from static context
    with pytest.raises(TypeError):
        Lsig.evaluate()

    with pytest.raises(TypeError):
        Lsig.checked(pt.abi.String())


def test_templated_logic_signature():
    class Lsig(LogicSignature):
        pubkey = TemplateVariable(pt.TealType.bytes)

        def evaluate(self):
            return pt.Seq(
                pt.Assert(pt.Len(self.pubkey)),
                pt.Int(1),
            )

    lsig = Lsig()

    assert len(lsig.template_variables) == 1
    assert len(lsig.methods) == 0
    assert len(lsig.attrs.keys()) == 2
    assert len(lsig.program) > 0

    assert "evaluate" in lsig.attrs
    assert "pubkey" in lsig.attrs

    assert lsig.pubkey.get_name() == "TMPL_PUBKEY"

    actual = lsig.pubkey._init_expr()
    expected = pt.ScratchStore(pt.Int(1), pt.Tmpl.Bytes("TMPL_PUBKEY"))

    with pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    # Should not fail
    lsig.evaluate()

    # Cant call it from static context
    with pytest.raises(TypeError):
        Lsig.evaluate()


def test_different_methods_logic_signature():
    class Lsig(LogicSignature):
        def evaluate(self):
            return pt.Seq(
                (s := pt.abi.String()).decode(pt.Txn.application_args[1]),
                self.abi_tester(s, output=(o := pt.abi.Uint64())),
                pt.Assert(self.internal_tester(o.get(), pt.Len(s.get()))),
                (sv := pt.ScratchVar()).store(pt.Int(1)),
                pt.Assert(self.internal_scratch_tester(sv, o.get())),
                pt.Int(1),
            )

        @internal(None)
        def abi_tester(self, s: pt.abi.String, *, output: pt.abi.Uint64):
            return output.set(pt.Len(s.get()))

        @internal(pt.TealType.uint64)
        def internal_tester(self, x: pt.Expr, y: pt.Expr) -> pt.Expr:
            return x * y

        @internal(pt.TealType.uint64)
        def internal_scratch_tester(self, x: pt.ScratchVar, y: pt.Expr) -> pt.Expr:
            return x.load() * y

        @internal
        def no_self_abi_tester(x: pt.abi.Uint64, y: pt.abi.Uint64) -> pt.Expr:  # type: ignore
            return x.get() * y.get()

        @internal(pt.TealType.uint64)
        def no_self_internal_tester(x: pt.Expr, y: pt.Expr) -> pt.Expr:  # type: ignore
            return x * y

    lsig = Lsig()

    assert len(lsig.template_variables) == 0
    assert len(lsig.methods) == 2
    assert len(lsig.attrs.keys()) == 6
    assert len(lsig.program) > 0

    assert "evaluate" in lsig.attrs

    # Should not fail
    lsig.evaluate()
    lsig.abi_tester(pt.abi.String(), output=pt.abi.Uint64())
    lsig.internal_tester(pt.Int(1), pt.Int(1))
    lsig.internal_scratch_tester(pt.ScratchVar(), pt.Int(1))
    Lsig.no_self_abi_tester(pt.abi.Uint64(), pt.abi.Uint64())

    lsig.no_self_internal_tester(pt.Int(1), pt.Int(1))
    Lsig.no_self_internal_tester(pt.Int(1), pt.Int(1))

    # Cant call it from bound context
    with pytest.raises(TypeError):
        lsig.no_self_abi_tester(pt.abi.Uint64(), pt.abi.Uint64())
