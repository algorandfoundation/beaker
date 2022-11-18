import pyteal as pt
from typing import Callable, cast, Any
from textwrap import dedent
import inspect
import ast

from .variable import Variable, write_into_var, read_from_var
from ._builtins import VariableType, ValueType, BuiltInTypes, BuiltInFuncs


def Unsupported(*feature):
    return Exception(f"This feature is not supported yet: {' '.join(feature)}")


class Preprocessor:
    def __init__(self, fn: Callable | ast.FunctionDef, obj: Any = None):

        if not isinstance(fn, ast.FunctionDef):
            self.src = dedent(inspect.getsource(fn))

            self.fn_name = fn.__name__

            tree = ast.parse(self.src, type_comments=True)
            self.definition = cast(ast.FunctionDef, tree.body[0])

            self.sig = inspect.signature(fn)
            self.orig_annotations = inspect.get_annotations(fn)
        else:
            self.fn_name = fn.name
            self.definition = fn

        self.obj = obj

        # Context
        self.funcs: dict[str, Callable] = BuiltInFuncs
        self.types: dict[str, tuple[ValueType, type]] = BuiltInTypes
        self.variables: dict[str, Variable] = {}

        self.args: dict[str, VariableType | None] = self._translate_args(
            self.definition.args
        )

        self.return_type: ValueType | None = None
        if self.definition.returns is not None:
            self.return_type = self._translate_annotation_type(self.definition.returns)

        self.return_stack_type = pt.TealType.none
        if type(self.return_type) is pt.TealType:
            self.return_stack_type = self.return_type
            self.funcs[self.fn_name] = pt.Subroutine(
                self.return_stack_type, name=self.fn_name
            )(self.subroutine())
        else:
            self.funcs[self.fn_name] = pt.ABIReturnSubroutine(
                self.subroutine(), overriding_name=self.fn_name
            )

        self.callable = self.funcs[self.fn_name]

    def subroutine(self):
        # Make a callable that passes args and sets output appropriately,
        # we modify its signature below
        def _impl(*args, **kwargs) -> pt.Expr:
            expr = self.function_body(*args)
            if "output" in kwargs:
                return write_into_var(kwargs["output"], expr)
            return expr

        translated_annotations = inspect.get_annotations(_impl)

        ######
        orig_annos = self.orig_annotations.copy()
        params = self.sig.parameters.copy()

        # Incoming args
        for k, v in params.items():
            if k == "self":
                continue

            params[k] = v.replace(annotation=self.args[k])
            orig_annos[k] = self.args[k]

        # If its an abi type we're returning, add output kwarg
        if self.return_type is not None and type(self.return_type) is not pt.TealType:
            params["output"] = inspect.Parameter(
                name="output",
                kind=inspect._ParameterKind.KEYWORD_ONLY,
                annotation=self.return_type,
            )
            orig_annos["output"] = self.return_type

        _impl.__name__ = self.fn_name
        _impl.__signature__ = self.sig.replace(
            parameters=list(params.values()), return_annotation=pt.Expr
        )
        _impl.__annotations__ = orig_annos | translated_annotations

        return _impl

    def function_body(self, *args) -> pt.Expr:
        """called at build time with arguments provided for variables"""

        stores: list[pt.Expr] = []
        for idx, name in enumerate(self.args.keys()):
            if name == "self":
                continue

            arg = args[idx]
            match arg:
                case pt.abi.BaseType():
                    self.variables[name] = Variable(name, arg, arg.type_spec())
                case pt.ScratchVar():
                    self.variables[name] = Variable(name, arg, arg.storage_type())
                case pt.Expr():
                    stores.append(self._write_storage_var(name, arg))
                case _:
                    raise Unsupported(
                        "idk what do do with this arg ", args[idx].__class__.__name__
                    )

        self.exprs = stores + [
            self._translate_ast(expr) for expr in self.definition.body
        ]
        return pt.Seq(*self.exprs)

    def _translate_args(self, args: ast.arguments) -> dict[str, VariableType | None]:
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

        arguments: dict[str, VariableType | None] = {}
        for arg in args.args:
            if arg.annotation is not None:
                anno_type = self._translate_annotation_type(arg.annotation)
                if type(anno_type) is pt.TealType:
                    arguments[arg.arg] = pt.Expr
                else:
                    arguments[arg.arg] = anno_type
            else:
                arguments[arg.arg] = None
        return arguments

    def _translate_annotation_type(self, _type: ast.AST) -> VariableType | None:
        match _type:
            case ast.Name():
                if _type.id in self.types:
                    t = self.types[_type.id][0]
                    if type(t) is pt.TealType:
                        return t
                    elif inspect.isclass(t) and issubclass(t, pt.abi.TypeSpec):
                        ts: pt.abi.TypeSpec = t()
                        return ts.annotation_type()
                else:
                    raise Unsupported("Type in translate type:", _type.id)

            case ast.Subscript():

                _slice: VariableType = self._translate_annotation_type(_type.slice)
                _container_type = self.types[_type.value.id][0]
                if not inspect.isclass(_container_type) or not issubclass(
                    _container_type, pt.abi.TypeSpec
                ):
                    raise Unsupported("Subscript with non typespec container")

                if (
                    _container_type is pt.abi.DynamicArrayTypeSpec
                    and _slice is not None
                ):
                    return pt.abi.type_spec_from_annotation(
                        pt.abi.DynamicArray[_slice]
                    ).annotation_type()

                raise Unsupported("annotation unsupported: ", _container_type, _slice)

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
                    if self.return_type is not None:
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
            case ast.Call():
                func: Callable[..., pt.Expr] = self._lookup_function(expr.func)
                args: list[pt.Expr] = [self._translate_ast(a) for a in expr.args]

                if len(expr.keywords) > 0:
                    raise Unsupported("keywords in Call")

                # This is weird
                if isinstance(func, pt.ABIReturnSubroutine | pt.SubroutineFnWrapper):
                    # If its an ABIReturnSubroutine or a SubroutineFnWrapper:
                    #   first map the args passed to a variable that the subr will accept
                    #   scratch/frames => abi type
                    from pyteal.ast.frame import FrameDig

                    for idx, arg in enumerate(args):
                        if isinstance(arg, pt.ScratchLoad):
                            args[idx] = self._lookup_or_alloc(
                                expr.args[idx], arg.type_of()
                            ).var
                        if isinstance(arg, FrameDig):
                            args[idx] = self._lookup_or_alloc(
                                expr.args[idx], arg.type_of()
                            ).var

                    ret_val = func(*args)

                    # The expression returned may have an output var,
                    # if it does, we have to load it back onto the stack or frame
                    # before returning an expression
                    if isinstance(ret_val, pt.abi.ReturnedValue):
                        return pt.Seq(
                            ret_val.computation, self._read_storage_var(expr.args[-1])
                        )

                    return ret_val

                return func(*args)
            case ast.If():
                if_test: pt.Expr = self._translate_ast(expr.test)
                if_body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]
                if_orelse: list[pt.Expr] = [self._translate_ast(e) for e in expr.orelse]
                return pt.If(if_test).Then(pt.Seq(*if_body)).Else(pt.Seq(*if_orelse))
            case ast.IfExp():
                ifExp_test: pt.Expr = self._translate_ast(expr.test)
                ifExp_body: pt.Expr = self._translate_ast(expr.body)
                ifExp_orelse: pt.Expr = self._translate_ast(expr.orelse)
                return pt.If(ifExp_test).Then(ifExp_body).Else(ifExp_orelse)
            case ast.For():
                if len(expr.orelse) > 0:
                    raise Unsupported("orelse in For")

                target: pt.ScratchVar | pt.abi.BaseType
                match expr.iter:
                    # We're iterating over some variable
                    case ast.Name():
                        var = self.variables[expr.iter.id]
                        match var.var:
                            case pt.abi.DynamicArray():
                                target: Variable = self._lookup_or_alloc(
                                    expr.target, var.var.type_spec().value_type_spec()
                                )

                                scratch_idx = pt.ScratchVar()
                                start = pt.Seq(
                                    scratch_idx.store(pt.Int(0)),
                                    var.var[pt.Int(0)].store_into(target.var),
                                )
                                cond = scratch_idx.load() < var.var.length()
                                step = pt.Seq(
                                    scratch_idx.store(scratch_idx.load() + pt.Int(1)),
                                    var.var[scratch_idx.load()].store_into(target.var),
                                )
                            case _:
                                # Check if its a list?
                                raise Unsupported("iter with unsupported type ", var)

                    # We're iterating over the result of a function call
                    case ast.Call():
                        call_target: Variable = self._lookup_or_alloc(expr.target)
                        iterator: pt.Expr = self._translate_ast(expr.iter)
                        start, cond, step = iterator(call_target.get_scratch_var())  # type: ignore
                    case _:
                        raise Unsupported("iter type in for loop: ", expr.iter)

                return pt.For(start, cond, step).Do(
                    *[self._translate_ast(e) for e in expr.body]
                )
            case ast.While():
                cond: pt.Expr = self._translate_ast(expr.test)  # type: ignore[no-redef]
                body: list[pt.Expr] = [self._translate_ast(e) for e in expr.body]  # type: ignore[no-redef]
                return pt.While(cond).Do(*body)
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
            case ast.AugAssign():
                aug_lookup_target: pt.Expr = self._read_storage_var(expr.target)
                aug_value: pt.Expr = self._translate_ast(expr.value)
                aug_op: Callable = self._translate_op(
                    expr.op, aug_lookup_target.type_of()
                )
                return self._write_storage_var(
                    expr.target, aug_op(aug_lookup_target, aug_value)
                )
            case ast.Assign():
                assign_value: pt.Expr = self._translate_ast(expr.value)
                assign_targets: list[Variable] = [
                    self._lookup_or_alloc(e, assign_value.type_of())
                    for e in expr.targets
                ]

                if len(assign_targets) > 1:
                    raise Unsupported(">1 target in Assign")

                return assign_targets[0].write(assign_value)

            case ast.AnnAssign():
                ann: VariableType = self._translate_annotation_type(expr.annotation)
                ann_target: Variable = self._lookup_or_alloc(expr.target, ann)
                ann_value: pt.Expr = self._translate_ast(expr.value)
                return ann_target.write(ann_value)
            case ast.FunctionDef():
                self.funcs[expr.name] = Preprocessor(expr).callable
                return pt.Seq()
            case ast.Name():
                match expr.ctx:
                    case ast.Load():
                        return self._read_storage_var(expr)
                    case ast.Store() | ast.Del():
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

    def _wrap_as(
        self, e: pt.Expr, t: type[pt.abi.BaseType]
    ) -> tuple[pt.abi.BaseType, pt.Expr]:
        ts = pt.abi.type_spec_from_annotation(t)
        v = ts.new_instance()
        return (v, write_into_var(v, e))

    def _lookup_or_alloc(
        self,
        name: ast.expr | str,
        ts: ValueType = None,
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
            self.variables[name_str] = Variable.from_type(name_str, ts)

        return self.variables[name_str]

    def _write_storage_var(self, name: ast.expr | str, val: pt.Expr) -> pt.Expr:
        v = self._lookup_or_alloc(name, val.type_of())
        if isinstance(v, Variable):
            return v.write(val)
        return write_into_var(v, val)

    def _read_storage_var(self, name: ast.expr) -> pt.Expr:
        v = self._lookup_or_alloc(name)
        if isinstance(v, Variable):
            return v.read()
        return read_from_var(v)

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
                    # Initialize abi return with static func, replace impl with bound version
                    static_func = inspect.getattr_static(self.obj, fn.attr)
                    if isinstance(static_func, pt.SubroutineFnWrapper):
                        return static_func

                    # TODO: this conflicts with the one we create in the init of Application
                    abi_meth = pt.ABIReturnSubroutine(static_func)
                    # Add bound version as implementation so `self` is provided
                    abi_meth.subroutine.implementation = getattr(self.obj, fn.attr)
                    return abi_meth
            case _:
                raise Unsupported("idk what to do with this")

        def _impl(*args):
            raise Unsupported("You triggered my trap card")

        return _impl
