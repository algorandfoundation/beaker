import pyteal as pt
from typing import Callable, cast, Any
from textwrap import dedent
import inspect
import ast

from ._builtins import BuiltInFuncs, BuiltInTypes


def Unsupported(*feature):
    return Exception(f"This feature is not supported yet: {' '.join(feature)}")


Variable = pt.ScratchVar | pt.abi.BaseType


class Preprocessor:
    def __init__(self, c: Callable, obj: Any = None):
        self.fn = c
        self.obj = obj

        self.src = dedent(inspect.getsource(c))
        self.tree = ast.parse(self.src)
        self.definition = cast(ast.FunctionDef, self.tree.body[0])

        self.funcs: dict[str, Callable] = BuiltInFuncs
        self.types: dict[str, type[pt.abi.BaseType]] = BuiltInTypes

        self.variables: dict[str, Variable] = {}

        self.args: dict[str, type[pt.abi.BaseType] | None] = self._translate_args(
            self.definition.args
        )

        self.returns: type[pt.abi.BaseType] | None = None

        if self.definition.returns is not None:
            self.returns = self._translate_type(self.definition.returns)

    def subroutine(self):
        # Make a callable that passes args and sets output appropriately,
        # we modify its signature below
        def _impl(*args, **kwargs) -> pt.Expr:
            if "output" in kwargs:
                return self.__write_to_var(kwargs["output"], self.expr(*args))
            else:
                return self.expr(*args)

        sig = inspect.signature(self.fn)
        orig_annotations = inspect.get_annotations(self.fn)
        translated_annotations = inspect.get_annotations(_impl)

        params = sig.parameters.copy()
        for k, v in params.items():
            if k == "self":
                continue
            if k not in self.args:
                raise Exception("Cant find arg?: ", k)

            translated_type = cast(type[pt.abi.BaseType], self.args[k])

            params[k] = v.replace(annotation=translated_type)
            orig_annotations[k] = translated_type

        if self.returns is not None:
            params["output"] = inspect.Parameter(
                name="output",
                kind=inspect._ParameterKind.KEYWORD_ONLY,
                annotation=self.returns,
            )
            orig_annotations["output"] = self.returns

        _impl.__name__ = self.fn.__name__
        _impl.__signature__ = sig.replace(
            parameters=list(params.values()), return_annotation=pt.Expr
        )
        _impl.__annotations__ = orig_annotations | translated_annotations

        return _impl

    def expr(self, *args) -> pt.Expr:
        """called at build time with arguments provided for variables"""
        for idx, name in enumerate(self.args.keys()):
            if name == "self":
                continue

            arg = args[idx]
            match arg:
                case pt.abi.BaseType():
                    self._provide_value(name, arg)
                case pt.Expr():
                    self._write_storage_var(name, arg)
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
                _value: type[pt.abi.BaseType] | None = self._translate_type(_type.value)
                _slice: type[pt.abi.BaseType] | None = self._translate_type(_type.slice)

                if _value is pt.abi.DynamicArray and _slice is not None:
                    da = pt.abi.DynamicArray[_slice]  # type: ignore
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
                if expr.value is not None:
                    val: pt.Expr = self._translate_ast(expr.value)
                    if self.returns is not None:
                        return val
                    return pt.Return(val)
                return pt.Return()

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

            # Ops
            case ast.Compare():
                left: pt.Expr = self._translate_ast(expr.left)
                ops: list[Callable] = [
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
                op: Callable = self._translate_op(expr.op, vals[0].type_of())
                return op(*vals)

            case ast.BinOp():
                left: pt.Expr = self._translate_ast(expr.left)  # type: ignore[no-redef]
                right: pt.Expr = self._translate_ast(expr.right)  # type: ignore[no-redef]
                op: Callable = self._translate_op(expr.op, left.type_of())  # type: ignore[no-redef]
                return op(left, right)

            case ast.UnaryOp():
                operand: pt.Expr = self._translate_ast(expr.operand)
                op: Callable = self._translate_op(expr.op, operand.type_of())  # type: ignore[no-redef]
                return op(operand)

            # Flow Control

            case ast.Call():
                func: Callable[..., pt.Expr] = self._lookup_function(expr.func)
                args: list[pt.Expr] = [self._translate_ast(a) for a in expr.args]

                print("FUNC: ", dir(func))
                print(type(func))

                from beaker.application import get_handler_config

                print(get_handler_config(func))

                if len(expr.keywords) > 0:
                    raise Unsupported("keywords in Call")

                print(args)
                return func(*args)

            case ast.If():
                test: pt.Expr = self._translate_ast(expr.test)  # type: ignore[no-redef]
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                orelse: list[pt.Expr] = [self._translate_ast(e) for e in expr.orelse]
                return pt.If(test).Then(pt.Seq(*body)).Else(pt.Seq(*orelse))

            case ast.For():
                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in For")

                target: pt.ScratchVar | pt.abi.BaseType
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
                                start = pt.Seq(
                                    idx.store(pt.Int(0)),
                                    var[pt.Int(0)].store_into(target),
                                )
                                cond = idx.load() < var.length()
                                step = pt.Seq(
                                    idx.store(idx.load() + pt.Int(1)),
                                    var[idx.load()].store_into(target),
                                )
                            case _:
                                # Check if its a list?
                                raise Unsupported("iter with unsupported type ", var)

                    # We're iterating over the result of a function call
                    case ast.Call():
                        call_target: Variable = self._lookup_or_alloc(expr.target)
                        iterator: pt.Expr = self._translate_ast(expr.iter)
                        start, cond, step = iterator(call_target)  # type: ignore
                    case _:
                        raise Unsupported("iter type in for loop: ", expr.iter)

                return pt.For(start, cond, step).Do(
                    *[self._translate_ast(e) for e in expr.body]
                )

            case ast.While():
                cond: pt.Expr = self._translate_ast(expr.test)  # type: ignore[no-redef]
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]  # type: ignore[no-redef]
                return pt.While(cond).Do(*body)

            # Types
            case ast.List():
                # Translate to vals and exprs that populate 'em
                elts: list[tuple[pt.abi.BaseType, pt.Expr]] = [
                    self._wrap_as(self._translate_ast(e), pt.abi.Uint64)
                    for e in expr.elts
                ]
                list_values: list[pt.abi.BaseType] = [e[0] for e in elts]
                exprs: list[pt.Expr] = [e[1] for e in elts]  # type: ignore[no-redef]
                return pt.Seq(
                    *exprs,
                    pt.abi.make(pt.abi.DynamicArray[pt.abi.Uint64]).set(list_values),  # type: ignore[arg-type]
                )

            # Var access
            case ast.AugAssign():
                lookup_target: pt.Expr = self._read_storage_var(expr.target)  # type: ignore[no-redef]
                value: pt.Expr = self._translate_ast(expr.value)  # type: ignore[no-redef]
                op: Callable = self._translate_op(expr.op, lookup_target.type_of())  # type: ignore[no-redef]
                return self._write_storage_var(expr.target, op(lookup_target, value))

            case ast.Assign():
                print(ast.dump(expr, indent=4))
                value: pt.Expr = self._translate_ast(expr.value)  # type: ignore[no-redef]
                targets: list[Variable] = [
                    self._lookup_or_alloc(e, value.type_of()) for e in expr.targets
                ]

                if len(targets) > 1:
                    raise Unsupported(">1 target in Assign")

                return self.__write_to_var(targets[0], value)

            # Namespace
            case ast.FunctionDef():
                raise Unsupported("Cant define a new func in a func")
                # body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                # def _impl(*args, **kwargs):
                #    return pt.Seq(*body)
                # _impl.__name__ = expr.name
                # self.funcs[expr.name] = pt.Subroutine(pt.TealType.uint64)(_impl)

            case ast.Name():
                match expr.ctx:
                    case ast.Load():
                        return self._read_storage_var(expr)
                    case ast.Store():
                        raise Unsupported("Where did you come from?")
                    case _:
                        raise Unsupported("ctx in name", expr.ctx)

            case _:
                print(ast.dump(expr, indent=4))
                print(expr.__dict__)
                raise Unsupported("Unhandled AST type: ", expr.__class__.__name__)

        return pt.Seq()

    def _translate_op(
        self, op: ast.AST, type: pt.TealType = pt.TealType.anytype
    ) -> Callable:
        if type == pt.TealType.bytes:
            match op:
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

    def _provide_value(self, name: str, val: Variable):
        self.variables[name] = val

    def _wrap_as(
        self, e: pt.Expr, t: type[pt.abi.BaseType]
    ) -> tuple[pt.abi.BaseType, pt.Expr]:
        ts = pt.abi.type_spec_from_annotation(t)
        v = ts.new_instance()
        return (v, self.__write_to_var(v, e))

    def _lookup_or_alloc(
        self, name: ast.expr | str, ts: pt.abi.TypeSpec | pt.TealType | None = None
    ) -> Variable:

        name_str = ""
        match name:
            case ast.Name():
                name_str = name.id
            case str():
                name_str = name
            case _:
                raise Unsupported(
                    "An name arg other than Name | str in lookup_or_alloc", name
                )

        if name_str not in self.variables:
            if ts is None:
                self.variables[name_str] = pt.ScratchVar()
            else:
                if isinstance(ts, pt.abi.TypeSpec):
                    self.variables[name_str] = ts.new_instance()
                else:
                    self.variables[name_str] = pt.ScratchVar(ts)

        return self.variables[name_str]

    def _write_storage_var(self, name: ast.expr | str, val: pt.Expr) -> pt.Expr:
        v = self._lookup_or_alloc(name)
        return self.__write_to_var(v, val)

    def __write_to_var(self, v: Any, val: pt.Expr) -> pt.Expr:
        match v:
            case pt.abi.String() | pt.abi.Address() | pt.abi.Uint() | pt.abi.DynamicBytes() | pt.abi.StaticBytes():
                return v.set(val)
            case pt.abi.BaseType():
                return v.decode(val)
            case pt.ScratchVar():
                return v.store(val)
            case _:
                raise Unsupported("idk what to do with a ", val)

    def _read_storage_var(self, name: ast.expr) -> pt.Expr:
        v = self._lookup_or_alloc(name)
        match v:
            case pt.abi.String() | pt.abi.Address() | pt.abi.DynamicBytes() | pt.abi.StaticBytes() | pt.abi.Uint():
                return v.get()
            case pt.abi.BaseType():
                if hasattr(v, "_stored_value"):
                    return v._stored_value.load()  # type: ignore[attr-defined]
                else:
                    return v.stored_value.load()
            case pt.ScratchVar():
                return v.load()
            case _:
                raise Unsupported("type in slot lookup: ", v)

    def _lookup_function(self, fn: ast.AST) -> Callable:
        match fn:
            case ast.Name():
                return self.funcs[fn.id]
            case ast.Attribute():
                name = ""
                match fn.value:
                    case ast.Name():
                        name = fn.value.id
                    case _:
                        raise Unsupported(
                            "In lookup_function: a value that isnt a Name type",
                            fn.value,
                        )

                if name == "self":
                    bound_func = getattr(self.obj, fn.attr)
                    static_func = inspect.getattr_static(self.obj, fn.attr)

                    abi_meth = pt.ABIReturnSubroutine(static_func)
                    abi_meth.subroutine.implementation = bound_func

                    return bound_func
            case _:
                raise Unsupported("idk what to do with this")

        def _impl(*args):
            raise Unsupported("You triggered my trap card")

        return _impl
