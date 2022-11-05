import pyteal as pt
from typing import cast, Any
from textwrap import dedent
import inspect
import ast

from .builtins import BuiltInFuncs, BuiltInTypes

Unsupported = lambda *feature: Exception(
    f"This feature is not supported yet: {' '.join(feature)}"
)


Variable = pt.ScratchVar | pt.abi.BaseType


class Preprocessor:
    def __init__(self, c: callable):
        self.orig = c
        self.src = dedent(inspect.getsource(c))
        self.tree = ast.parse(self.src)
        self.definition = cast(ast.FunctionDef, self.tree.body[0])

        self.funcs: dict[str, callable] = BuiltInFuncs
        self.types: dict[str, pt.abi.BaseType] = BuiltInTypes

        self.variables: dict[str, Variable] = {}

        self.args: dict[str, type[pt.abi.BaseType] | None] = self._translate_args(
            self.definition.args
        )

        self.returns: type[pt.abi.BaseType] | None = None

        if self.definition.returns is not None:
            self.returns: type[pt.abi.BaseType] = self._translate_type(
                self.definition.returns
            )

    def expr(self, *args, **kwargs):
        """called at build time with slots provided"""
        for idx, name in enumerate(self.args.keys()):
            if name == "self":
                continue

            arg = args[idx]
            match arg:
                case pt.abi.BaseType():
                    self._provide_value(name, arg)
                case _:
                    raise Unsupported(
                        "idk what do do with this arg ", args[idx].__class__.__name__
                    )

        self.exprs = [self._translate_ast(expr) for expr in self.definition.body]
        return pt.Seq(*self.exprs)

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
                arguments[arg.arg] = self._translate_type(arg.annotation)
            else:
                arguments[arg.arg] = None
        return arguments

    def _translate_type(self, _type: ast.AST) -> type[pt.abi.BaseType] | None:
        match _type:
            case ast.Name():
                if _type.id in self.types:
                    return self.types[_type.id]
                else:
                    raise Unsupported("Type in translate type:", _type.id)

            case ast.Subscript():
                _value: type[pt.abi.BaseType] = self._translate_type(_type.value)
                _slice: type[pt.abi.BaseType] = self._translate_type(_type.slice)

                if _value is pt.abi.DynamicArray:
                    da = pt.abi.DynamicArray[_slice]
                    return da
                else:
                    raise Unsupported("Non dynamic array in subscript of args", _type)

            case _:
                raise Unsupported("arg type in args: ", _type.__class__.__name__)

    def _translate_ast(self, expr: ast.AST) -> pt.Expr:
        match expr:
            case ast.Expr():
                return self._translate_ast(expr.value)
            case ast.Constant():
                match expr.value:
                    case bool():
                        return pt.Int(int(expr.value))
                    case int():
                        return pt.Int(expr.value)
                    case bytes() | str():
                        return pt.Bytes(expr.value)
            case ast.Return():
                val: pt.Expr = self._translate_ast(expr.value)
                if self.returns is not None:
                    return val
                return pt.Return(val)

            case ast.Assert():
                test: pt.Expr = self._translate_ast(expr.test)

                msg: str | None = None
                if expr.msg is not None:
                    # TODO: translate ast returns Bytes expr
                    msg = cast(ast.Constant, expr.msg).value
                    # msg: pt.Expr = self._translate_ast(expr.msg)
                    # if msg.type_of() != pt.TealType.bytes:
                    #    raise Unsupported("Need bytes for assert message")

                return pt.Assert(test, comment=msg)

            ## Ops
            case ast.Compare():
                left: pt.Expr = self._translate_ast(expr.left)
                ops: list[callable] = [
                    self._translate_op(e, left.type_of()) for e in expr.ops
                ]
                comparators: list[pt.Expr] = [
                    self._translate_ast(e) for e in expr.comparators
                ]

                if len(ops) > 1:
                    raise Unsupported(">1 op in Compare")
                if len(comparators) > 1:
                    raise Unsupported(">1 comparator in Compare")

                return ops[0](left, comparators[0])

            case ast.BoolOp():
                vals: list[pt.Expr] = [self._translate_ast(v) for v in expr.values]
                op: callable = self._translate_op(expr.op, vals[0].type_of())
                return op(*vals)

            case ast.BinOp():
                left: pt.Expr = self._translate_ast(expr.left)
                right: pt.Expr = self._translate_ast(expr.right)
                op: callable = self._translate_op(expr.op, left.type_of())
                return op(left, right)

            case ast.UnaryOp():
                operand: pt.Expr = self._translate_ast(expr.operand)
                op: callable = self._translate_op(expr.op, operand.type_of())
                return op(operand)

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
                orelse: list[pt.Expr] = [self._translate_ast(e) for e in expr.orelse]
                return pt.If(test).Then(pt.Seq(*body)).Else(pt.Seq(*orelse))

            case ast.For():
                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in For")

                target: pt.ScratchVar | pt.abi.BaseType
                iter: callable[tuple[pt.Expr, pt.Expr, pt.Expr]]

                match expr.iter:
                    # We're iterating over some variable
                    case ast.Name():
                        var = self.variables[expr.iter.id]
                        match var:
                            case pt.abi.DynamicArray():
                                target = self._lookup_or_alloc(
                                    expr.target, var.type_spec().value_type_spec()
                                )
                                idx = pt.ScratchVar()
                                init = pt.Seq(
                                    idx.store(pt.Int(0)),
                                    var[pt.Int(0)].store_into(target),
                                )
                                cond = idx.load() < var.length()
                                step = pt.Seq(
                                    idx.store(idx.load() + pt.Int(1)),
                                    var[idx.load()].store_into(target),
                                )
                                iter = (init, cond, step)
                            case _:
                                # Check if its a list?
                                raise Unsupported("iter with unsupported type ", var)

                    # We're iterating over the result of a function call
                    case ast.Call():
                        target = self._lookup_or_alloc(expr.target)
                        iter = self._translate_ast(expr.iter)(target)
                    case _:
                        raise Unsupported("iter type in for loop: ", expr.iter)

                return pt.For(*iter).Do([self._translate_ast(e) for e in expr.body])

            case ast.While():
                cond: pt.Expr = self._translate_ast(expr.test)
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                return pt.While(cond).Do(*body)

            ### Var access
            case ast.AugAssign():
                target: pt.ScratchSlot = self._lookup_storage_var(expr.target)
                value: pt.Expr = self._translate_ast(expr.value)
                op: callable = self._translate_op(expr.op, value.type_of())
                return target.store(op(target.load(), value))

            case ast.Assign():
                value: pt.Expr = self._translate_ast(expr.value)
                targets: list[Variable] = [
                    self._lookup_or_alloc(e, value.type_of()) for e in expr.targets
                ]

                if len(targets) > 1:
                    raise Unsupported(">1 target in Assign")

                return targets[0].store(value)

            ## Namespace
            case ast.FunctionDef():
                raise Unsupported("Cant define a new func in a func")
                # body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                # def _impl(*args, **kwargs):
                #    return pt.Seq(*body)
                # _impl.__name__ = expr.name
                # self.funcs[expr.name] = pt.Subroutine(pt.TealType.uint64)(_impl)

            case ast.Name():
                match expr.ctx:
                    case ast.Store():
                        raise Unsupported("wat")
                    case ast.Load():

                        v = self._lookup_storage_var(expr)
                        return v.load()
                    case _:
                        raise Unsupported("ctx in name" + expr.ctx)

            case _:
                print(ast.dump(expr, indent=4))
                print(expr.__dict__)
                raise Unsupported("Unhandled AST type: " + expr.__class__.__name__)

    def _translate_op(
        self, op: ast.AST, type: pt.TealType = pt.TealType.anytype
    ) -> callable:
        if type == pt.TealType.bytes:
            match op:
                ### Ops
                case ast.Mult():
                    return pt.BytesMul
                case ast.Eq():
                    return pt.BytesEq
                case ast.NotEq():
                    return pt.BytesNeq
                case ast.Gt():
                    return pt.BytesGt
                case ast.GtE():
                    return pt.BytesGe
                case ast.Lt():
                    return pt.BytesLt
                case ast.LtE():
                    return pt.BytesLe
                case ast.Sub():
                    return pt.BytesMinus
                case ast.Mod():
                    return pt.BytesMod
                case ast.BitOr():
                    return pt.BytesOr
                case ast.BitAnd():
                    return pt.BytesAnd
                case ast.BitXor():
                    return pt.BytesXor
                case ast.Add():
                    return pt.BytesAdd
                case ast.Div() | ast.FloorDiv():
                    return pt.BytesDiv
                case ast.Pow() | ast.RShift() | ast.LShift():
                    raise Unsupported("Unsupported op: ", op.__class__.__name__)
                case _:
                    raise Unsupported("Unsupported op: ", op.__class__.__name__)
        else:
            match op:
                ### Ops
                case ast.And():
                    return pt.And
                case ast.Or():
                    return pt.Or
                case ast.Not():
                    return pt.Not
                case ast.Mult():
                    return pt.Mul
                case ast.Pow():
                    return pt.Exp
                case ast.Eq():
                    return pt.Eq
                case ast.NotEq():
                    return pt.Neq
                case ast.Gt():
                    return pt.Gt
                case ast.GtE():
                    return pt.Ge
                case ast.Lt():
                    return pt.Lt
                case ast.LtE():
                    return pt.Le
                case ast.Sub():
                    return pt.Minus
                case ast.Mod():
                    return pt.Mod
                case ast.BitOr():
                    return pt.BitwiseOr
                case ast.BitAnd():
                    return pt.BitwiseAnd
                case ast.BitXor():
                    return pt.BitwiseXor
                case ast.RShift():
                    return pt.ShiftRight
                case ast.LShift():
                    return pt.ShiftLeft
                case ast.Add():
                    return pt.Add
                case ast.Div() | ast.FloorDiv():
                    return pt.Div
                case _:
                    raise Unsupported("Unsupported op: ", op.__class__.__name__)

    def _provide_value(self, name: str, val: pt.ScratchVar):
        self.variables[name] = val

    def _lookup_or_alloc(
        self, name: ast.Name, ts: pt.abi.TypeSpec | pt.TealType | None = None
    ) -> Variable:
        if name.id not in self.variables:
            if ts is None:
                self.variables[name.id] = pt.ScratchVar()
            else:
                if isinstance(ts, pt.abi.TypeSpec):
                    self.variables[name.id] = ts.new_instance()
                else:
                    self.variables[name.id] = pt.ScratchVar(ts)

        return self.variables[name.id]

    def _lookup_storage_var(self, name: ast.Name) -> pt.ScratchVar:
        v = self._lookup_or_alloc(name)
        match v:
            case pt.abi.BaseType():
                return v._stored_value
            case pt.ScratchVar():
                return v
            case _:
                raise Unsupported("type in slot lookup: ", v)

    def _lookup_storage_type(
        self, name: ast.Name
    ) -> pt.TealType | type[pt.abi.BaseType]:
        v = self.variables[name.id]
        match v:
            case pt.abi.BaseType():
                return v.__class__
            case pt.ScratchVar():
                return v.storage_type()
            case _:
                raise Unsupported("var type in lookup type", v)

    def _lookup_function(self, name: ast.Name | ast.Attribute) -> callable:
        return self.funcs[name.id]
