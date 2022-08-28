import pytest
import pyteal as pt
from beaker.decorators import internal
from beaker.logic_signature import LogicSignature


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
    lsig.checked(pt.abi.String())
    lsig.evaluate()

    # Cant call it from static context
    with pytest.raises(TypeError):
        Lsig.evaluate()

    with pytest.raises(TypeError):
        Lsig.checked(pt.abi.String())
