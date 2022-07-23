from typing import Literal
from pyteal import *
from beaker.contracts import OpUp
from beaker.consts import AppCallBudget, MaxOps

from beaker.decorators import ResolvableArguments, handler


def requires(*args: Expr):
    # Denote this as metadata
    return Assert(*args)


def nonzero(e: Expr):
    # denote this as metadata
    match e:
        case Int():
            return e
        case Bytes():
            return Len(e)
        case abi.Uint():
            return e.get()
        case abi.String():
            return e.length()

def between(v: Expr, min: Expr, max: Expr):
    if min == 0:
        return v<max
    else:
        return And(v>min, v<max)

def equal(a: Expr, b: Expr):
    return a == b

def get_opcost(e: Expr):
    # Need to figure out how to expose op cost in pyteal
    return Int(0)


def num_opups(expected_cost: Int):
    # TODO: take into account current budget?
    return expected_cost / AppCallBudget


class ExpensiveApp(OpUp):
    """Do expensive work to demonstrate inheriting from OpUp"""

    @handler(resolvable=ResolvableArguments(opup_app=OpUp.opup_app_id))
    def hash_it(
        self,
        input: abi.String,
        iters: abi.Uint64,
        opup_app: abi.Application,
        *,
        output: abi.StaticArray[abi.Byte, Literal[32]],
    ):

        hash_routine = Seq(
            (current := ScratchVar()).store(input.get()),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < iters.get(),
                i.store(i.load() + Int(1)),
            ).Do(current.store(Sha256(current.load()))),
            output.decode(current.load()),
        )

        opcost = get_opcost(hash_routine)

        return Seq(
            requires(
                nonzero(input),
                between(iters, 0, MaxOps / opcost),
                equal(opup_app.application_id(), self.opup_app_id),
            ),
            self.call_opup(num_opups(opcost*iters)),
            hash_routine,
        )
