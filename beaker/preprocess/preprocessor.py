import pyteal as pt
from typing import cast, Any
from textwrap import dedent
import inspect
import ast

from .builtins import BuiltInFuncs, BuiltInTypes

Unsupported = lambda feature: Exception(f"This feature is not supported yet: {feature}")


class Preprocessor:
    def __init__(self, c: callable):
        self.orig = c
        self.src = dedent(inspect.getsource(c))
        self.tree = ast.parse(self.src)
        self.definition = cast(ast.FunctionDef, self.tree.body[0])

        self.funcs: dict[str, callable] = BuiltInFuncs
        self.types: dict[str, pt.abi.BaseType] = BuiltInTypes

        self.variables: dict[str, pt.ScratchSlot] = {}

        self.args: dict[str, type[pt.abi.BaseType] | None] = self._translate_args(
            self.definition.args
        )

        self.returns: type[pt.abi.BaseType] | None = None

        if self.definition.returns is not None:
            self.returns: type[pt.abi.BaseType] = self._translate_return_type(
                self.definition.returns
            )

        exprs = [self._translate_ast(expr) for expr in self.definition.body]
        self.body: pt.Expr = pt.Seq(*exprs)
        print(self.body.type_of())

    def _translate_args(
        self, args: ast.arguments
    ) -> dict[str, type[pt.abi.BaseType] | None]:
        if args.kwarg is not None:
            raise Unsupported("kwarg in args")
        if args.vararg is not None:
            raise Unsupported("vararg in args")
        if len(args.posonlyargs) > 0:
            raise Unsupported("posonly in args")
        if len(args.kwonlyargs) > 0:
            raise Unsupported("kwonly in args")
        if len(args.kw_defaults) > 0:
            raise Unsupported("kwdefaults in args")
        if len(args.defaults) > 0:
            raise Unsupported("defaults in args")

        arguments: dict[str, Any] = {}
        for arg in args.args:
            if arg.annotation is not None:
                match arg.annotation:
                    case ast.Name():
                        arguments[arg.arg] = self.types[arg.annotation.id]
                    case _:
                        raise Unsupported(
                            "arg type in args: ", arg.annotation.__class__.__name__
                        )
            else:
                arguments[arg.arg] = None
        return arguments

    def _translate_return_type(self, ret: ast.Name) -> type[pt.abi.BaseType]:
        return self.types[ret.id]

    def _translate_ast(self, expr: ast.AST) -> pt.Expr:
        match expr:
            case ast.Expr():
                return self._translate_ast(expr.value)
            case ast.Constant():
                match expr.value:
                    case int():
                        return pt.Int(expr.value)
                    case bytes() | str():
                        return pt.Bytes(expr.value)

            case ast.Return():
                val: pt.Expr = self._lookup_value(expr.value)
                if self.returns is not None:
                    return val

                return pt.Return(val)

            case ast.Compare():
                left: pt.Expr = self._lookup_value(expr.left)
                ops: list[callable] = [
                    self._translate_op(e, left.type_of()) for e in expr.ops
                ]
                comparators: list[pt.Expr] = [
                    self._lookup_value(e) for e in expr.comparators
                ]

                if len(ops) > 1:
                    raise Unsupported(">1 op in Compare")
                if len(comparators) > 1:
                    raise Unsupported(">1 comparator in Compare")

                return ops[0](left, comparators[0])

            case ast.BinOp():
                left: pt.Expr = self._lookup_value(expr.left)
                right: pt.Expr = self._lookup_value(expr.right)
                op: callable = self._translate_op(expr.op, left.type_of())
                return op(left, right)

            ## Flow Control

            case ast.Call():
                func: callable = self._lookup_function(expr.func)
                args: list[pt.Expr] = [self._translate_ast(a) for a in expr.args]

                if len(expr.keywords) > 0:
                    raise Unsupported("keywords in Call")

                return func(*args)

            case ast.If():
                test: pt.Expr = self._translate_ast(expr.test)
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]

                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in If")

                return pt.If(test).Then(*body)

            case ast.For():
                target: pt.ScratchVar = self._lookup_storage(expr.target)
                iter: tuple[pt.Expr, pt.Expr, pt.Expr] = self._translate_iter(
                    expr.iter, target
                )
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]

                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in For")

                start, cond, step = iter
                return pt.For(start, cond, step).Do(body)

            case ast.While():
                cond: pt.Expr = self._translate_ast(expr.test)
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                return pt.While(cond).Do(*body)

            ### Var access
            case ast.AugAssign():
                target: pt.ScratchVar = self._lookup_storage(expr.target)
                value: pt.Expr = self._translate_ast(expr.value)
                op: callable = self._translate_op(expr.op, value.type_of())
                return target.store(op(target.load(), value))

            case ast.Assign():
                targets: list[pt.ScratchVar] = [
                    self._lookup_storage(e) for e in expr.targets
                ]
                value: pt.Expr = self._translate_ast(expr.value)
                if len(targets) > 1:
                    raise Unsupported(">1 target in Assign")

                return targets[0].store(value)

            case _:
                print(ast.dump(expr, indent=4))
                print(expr.__dict__)
                raise Unsupported("Unhandled AST type: " + expr.__class__.__name__)

    def _translate_iter(
        self, iter: ast.AST, target: pt.Expr
    ) -> tuple[pt.Expr, pt.Expr, pt.Expr]:
        e2 = self._translate_ast(iter)
        return e2(target)

    def _translate_op(self, op: ast.AST, type: pt.TealType) -> callable:
        match op:
            ### Ops
            case ast.Mult():
                return pt.Mul
            case ast.Pow():
                return pt.Exp
            case ast.Eq():
                return pt.Eq
            case ast.Gt():
                return pt.Gt
            case ast.Lt():
                return pt.Lt
            case ast.Sub():
                return pt.Minus
            case ast.Add():
                match type:
                    case pt.TealType.bytes:
                        return pt.Concat
                    case pt.TealType.uint64:
                        return pt.Add
            case ast.Div() | ast.FloorDiv():
                return pt.Div
            case _:
                raise Unsupported("Unsupported op: ", op.__class__.__name__)

    def _lookup_value(self, val: ast.Name | ast.Constant) -> pt.Expr:
        print(ast.dump(val, indent=4))

        match val:
            case ast.Name():
                return self._lookup_storage(val).load()
            case ast.Constant():
                return self._translate_ast(val)

    def _lookup_storage(self, name: ast.Name) -> pt.ScratchVar:
        if name.id not in self.variables:
            self.variables[name.id] = pt.ScratchVar()

        print("LOOKUP: ", name.id, self.variables[name.id].index())
        return self.variables[name.id]

    def _lookup_function(self, name: ast.Name | ast.Attribute) -> callable:
        return self.funcs[name.id]
