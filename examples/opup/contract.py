from typing import Literal, Annotated
from pyteal import abi, ScratchVar, Seq, Assert, Int, For, Sha256, Expr, And, Bytes, Len
from beaker.decorators import external, ResolvableArguments
from beaker.contracts import OpUp
from beaker.consts import AppCallBudget, MaxOps


def nonzero():
    def _impl(e: Expr):
        match e:
            case Int():
                return e
            case Bytes():
                return Len(e)
            case abi.Uint():
                return e.get()
            case abi.String():
                return e.length()

    return _impl


def between(v: Expr):
    def __impl(min: Expr, max: Expr):
        if min == 0:
            return v < max
        else:
            return And(v > min, v < max)

    return __impl


def equal(field: type[abi.BaseType]):
    def _impl(b: abi.BaseType):
        # todo
        return field == b

    return _impl


def get_op_cost(e: Expr):
    # Need to figure out how to expose op cost in pyteal
    return Int(0)


def num_opups(expected_cost: Int):
    # TODO: take into account current budget?
    return expected_cost / AppCallBudget


Checked = Annotated


class ExpensiveApp(OpUp):
    """Do expensive work to demonstrate inheriting from OpUp"""

    @external(resolvable=ResolvableArguments(opup_app=OpUp.opup_app_id))
    def hash_it(
        self,
        input: Checked[abi.String, nonzero()],
        iters: Checked[abi.Uint64, nonzero()],
        opup_app: Checked[abi.Application, equal(OpUp.opup_app_id)],
        *,
        output: abi.StaticArray[abi.Byte, Literal[32]],
    ):
        return Seq(
            Assert(opup_app.application_id() == self.opup_app_id),
            self.call_opup(Int(255)),
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            current.load(),
        )


e = ExpensiveApp()
print(e.approval_program)
print(e.hints)
