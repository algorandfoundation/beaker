from typing import Literal, Annotated, get_type_hints
from pyteal import *
from beaker.contracts import OpUp
from beaker.consts import AppCallBudget, MaxOps

from beaker.decorators import ResolvableArguments, handler


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

    @handler
    def hash_it(
        self,
        input: Checked[abi.String, nonzero()],
        iters: Checked[abi.Uint64, nonzero()],
        _: Checked[abi.Application, equal(OpUp.opup_app_id)],
        *,
        output: abi.StaticArray[abi.Byte, Literal[32]],
    ):
        _hasher = Seq(
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            current.load(),
        )
        return Seq(
            self.call_opup(num_opups(get_op_cost(_hasher) * iters.get())),
            output.decode(_hasher),
        )


e = ExpensiveApp()
print(e.approval_program)
print(e.hints)
