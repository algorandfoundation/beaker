from pyteal import *
from typing import cast
import inspect
import ast


Unsupported = lambda feature: Exception(f"This feature is not supported yet: {feature}")


def _range(iters: Int) -> callable:
    def _impl(sv: ScratchVar):
        return (sv.store(Int(0)), sv.load() < iters, sv.store(sv.load() + Int(1)))

    return _impl


class Preprocessor:
    def __init__(self, c: callable):
        self.orig = c
        self.src = inspect.getsource(c).strip()
        self.tree = ast.parse(self.src)
        self.definition = cast(ast.FunctionDef, self.tree.body[0])
        self.arguemnts = self.definition.args

        self.funcs: dict[str, callable] = {"range": _range}

        self.variables: dict[str, ScratchSlot] = {}
        self.slot = 0

        self.body: list[Expr] = [
            self._translate_ast(expr) for expr in self.definition.body
        ]
        self.expr = Seq(*self.body)

    def _translate_ast(self, expr: ast.AST) -> Expr:
        print(ast.dump(expr, indent=4))
        print(expr.__dict__)

        match expr:
            case ast.Return():
                return Return(self._lookup_value(expr.value))
            case ast.Constant():
                match expr.value:
                    case int():
                        return Int(expr.value)
                    case bytes() | str():
                        return Bytes(expr.value)
            case ast.If():
                test: Expr = self._translate_ast(expr.test)
                body: list[Expr] = [self._translate_ast(e) for e in expr.body]

                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in If")

                return If(test).Then(*body)

            case ast.For():
                target: ScratchVar = self._lookup_storage(expr.target)
                iter: tuple[Expr, Expr, Expr] = self._translate_iter(expr.iter, target)
                body: list[Expr] = [self._translate_ast(e) for e in expr.body]

                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in For")

                start, cond, step = iter
                return For(start, cond, step).Do(body)

            case ast.While():
                cond: Expr = self._translate_ast(expr.test)
                body: list[Expr] = [self._translate_ast(e) for e in expr.body]
                return While(cond).Do(*body)

            case ast.Call():
                func: callable = self._lookup_function(expr.func)
                args: list[Expr] = [self._translate_ast(a) for a in expr.args]

                if len(expr.keywords) > 0:
                    raise Unsupported("keywords in Call")

                return func(*args)

            case ast.Compare():
                left: Expr = self._lookup_value(expr.left)
                ops: list[callable] = [
                    self._translate_op(e, left.type_of()) for e in expr.ops
                ]
                comparators: list[Expr] = [
                    self._lookup_value(e) for e in expr.comparators
                ]

                if len(ops) > 1:
                    raise Unsupported(">1 op in Compare")
                if len(comparators) > 1:
                    raise Unsupported(">1 comparator in Compare")

                return ops[0](left, comparators[0])

            case ast.BinOp():
                left: Expr = self._lookup_value(expr.left)
                right: Expr = self._lookup_value(expr.right)
                op: callable = self._translate_op(expr.op, left.type_of())
                return op(left, right)

            ### Var access
            case ast.AugAssign():
                target: ScratchVar = self._lookup_storage(expr.target)
                value: Expr = self._translate_ast(expr.value)
                op: callable = self._translate_op(expr.op, value.type_of())
                return target.store(op(target.load(), value))

            case ast.Assign():
                targets: list[ScratchVar] = [
                    self._lookup_storage(e) for e in expr.targets
                ]
                value: Expr = self._translate_ast(expr.value)
                if len(targets) > 1:
                    raise Unsupported(">1 target in Assign")

                return targets[0].store(value)

            case _:
                raise Unsupported(expr.__class__.__name__)

    def _translate_iter(self, iter: ast.AST, target: Expr) -> tuple[Expr, Expr, Expr]:
        e2 = self._translate_ast(iter)
        return e2(target)

    def _translate_op(self, op: ast.AST, type: TealType) -> callable:
        match op:
            ### Ops
            case ast.Mult():
                return Mul
            case ast.Pow():
                return Exp
            case ast.Eq():
                return Eq
            case ast.Gt():
                return Gt
            case ast.Lt():
                return Lt
            case ast.Sub():
                return Minus
            case ast.Add():
                match type:
                    case TealType.bytes:
                        return Concat
                    case TealType.uint64:
                        return Add
            case ast.Div() | ast.FloorDiv():
                return Div

    def _lookup_value(self, val: ast.Name | ast.Constant) -> Expr:
        match val:
            case ast.Name():
                return self._lookup_storage(val).load()
            case ast.Constant():
                return self._translate_ast(val)

    def _lookup_storage(self, name: ast.Name) -> ScratchVar:
        if name.id not in self.variables:
            self.variables[name.id] = ScratchVar()
        return self.variables[name.id]

    def _lookup_function(self, name: ast.Name) -> callable:
        return self.funcs[name.id]
