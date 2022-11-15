import inspect
from typing import Callable
from pyteal.ast.return_ import ExitProgram
import pyteal as pt
import beaker as bkr
import ast


# Note: Wrapping an ast node in `Expr(value=xxx)` pushes it to the next line


def Unsupported(*feature):
    return Exception(f"This feature is not supported yet: {' '.join(feature)}")


op_lookup = {str(op): op.name for op in pt.Op}


class Unprocessor:
    def __init__(
        self, e: pt.Expr, name: str, methods: dict[str, pt.Subroutine], *args, **kwargs
    ):
        self.expr = e
        # self.slots_in_use: dict[int, pt.ScratchSlot] = {}

        self.methods = methods

        self.native_ast = ast.fix_missing_locations(
            ast.Module(
                body=[
                    ast.FunctionDef(
                        name=name,
                        args=ast.arguments(
                            args=[],
                            posonlyargs=[],
                            vararg=None,
                            kwonlyargs=[],
                            kw_defaults=[],
                            kwarg=None,
                            defaults=[],
                        ),
                        body=self._translate_ast(pt.Seq(e)),
                        decorator_list=[],
                        returns=None,
                        lineno=1,
                    )
                ],
                type_ignores=[],
            )
        )

    def _translate_ast(self, e: pt.Expr) -> ast.AST:
        match e:
            case pt.Seq():
                return [self._translate_ast(expr) for expr in e.args]
            case pt.Cond():
                conditions: list[ast.If] = []
                for arg in e.args:
                    test: ast.AST = self._translate_ast(arg[0])
                    body: ast.AST = self._translate_ast(arg[1])
                    conditions.append(ast.If(test=test, body=body, orelse=[]))

                conditions[0].orelse = conditions[1:]
                return conditions[0]

            case pt.If():
                test: ast.AST = self._translate_ast(e.cond)
                body: ast.AST = ast.Expr(value=self._translate_ast(e.thenBranch))
                orelse: list[ast.AST] = []
                if e.elseBranch is not None:
                    orelse.append(ast.Expr(value=self._translate_ast(e.elseBranch)))
                return ast.If(test=test, body=body, orelse=orelse)

            case pt.NaryExpr():
                nary_op: ast.AST = self._translate_op(e.op, e.outputType)
                match nary_op:
                    case ast.boolop():
                        return ast.BoolOp(
                            op=nary_op,
                            values=[self._translate_ast(expr) for expr in e.args],
                        )
                    case _:
                        # Get the first one, then binop up the rest
                        current_val: ast.AST = self._translate_ast(e.args[0])
                        for expr in e.args[1:]:
                            current_val = ast.BinOp(
                                left=current_val,
                                right=self._translate_ast(expr),
                                op=nary_op,
                            )
                        return current_val

            case pt.UnaryExpr():
                unary_val: ast.AST = self._translate_ast(e.arg)
                match e.op:
                    case pt.Op.pop:
                        # TODO: right now we just assign the result of pop to underscore
                        return ast.Assign(
                            value=unary_val,
                            targets=[ast.Name(id="_", ctx=ast.Store())],
                        )
                    case pt.Op.len:
                        return ast.Call(
                            func=ast.Name(id="len", ctx=ast.Load()),
                            args=[unary_val],
                            keywords={},
                        )

                unary_op: ast.AST = self._translate_op(e.op, e.type_of())
                return ast.UnaryOp(operand=unary_val, op=unary_op)

            case pt.BinaryExpr():

                match e.op:
                    case pt.Op.getbyte:
                        return ast.Call(
                            func=ast.Name(id="getbyte", ctx=ast.Load()),
                            args=[
                                self._translate_ast(e.argLeft),
                                self._translate_ast(e.argRight),
                            ],
                            keywords={},
                        )

                binary_op: ast.AST = self._translate_op(e.op, e.type_of())
                match binary_op:
                    case ast.cmpop():
                        return ast.Compare(
                            ops=[binary_op],
                            left=self._translate_ast(e.argLeft),
                            comparators=[self._translate_ast(e.argRight)],
                        )
                return ast.BinOp(
                    op=binary_op,
                    left=self._translate_ast(e.argLeft),
                    right=self._translate_ast(e.argRight),
                )

            case pt.Assert():
                test: ast.AST = self._translate_ast(e.cond[0])
                for cond in e.cond[1:]:
                    test = ast.BoolOp(
                        values=[test, self._translate_ast(cond)], op=ast.And()
                    )
                return ast.Assert(test=test)

            case pt.SubroutineCall():
                fn_name: str = e.subroutine.name()
                call_args: list[ast.AST] = [self._translate_ast(a) for a in e.args]
                return ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id=fn_name, ctx=ast.Load()),
                        args=call_args,
                        keywords={},
                    )
                )

            case pt.TxnExpr():
                return ast.Call(
                    func=ast.Name(id=f"txn_{e.field.name}", ctx=ast.Load()),
                    args=[],
                    keywords={},
                )

            case pt.TxnaExpr():
                arg: ast.AST
                match e.index:
                    case int():
                        arg = ast.Constant(value=e.index)
                    case _:
                        arg = self._translate_ast(e.index)

                return ast.Call(
                    func=ast.Name(id=f"txn_{e.field.name}", ctx=ast.Load()),
                    args=[arg],
                    keywords={},
                )

            case pt.ScratchStore():
                slot_id = 0
                if e.slot is not None:
                    slot_id = e.slot.id
                else:
                    raise Unsupported("Store with no slot id?", e)

                return ast.Assign(
                    value=self._translate_ast(e.value),
                    targets=[ast.Name(id=f"var_{slot_id}", ctx=ast.Store())],
                    lineno=0,
                )

            case pt.ScratchLoad():
                slot_id = 0
                if e.slot is not None:
                    slot_id = e.slot.id
                else:
                    raise Unsupported("Load with no slot id?", e)

                return ast.Name(f"var_{slot_id}", ctx=ast.Load())

            case pt.MethodSignature():
                return ast.Call(
                    func=ast.Name(id="method_signature", ctx=ast.Load()),
                    args=[ast.Constant(value=e.methodName)],
                    keywords={},
                )

            case pt.EnumInt():
                return ast.Name(id="OnComplete." + e.name, ctx=ast.Load())

            case pt.App():
                return ast.Call(
                    func=ast.Name(id="App." + e.field.name, ctx=ast.Load()),
                    args=[self._translate_ast(ex) for ex in e.args],
                    keywords={},
                )

            case pt.Global():
                return ast.Call(
                    func=ast.Name(id="Global." + e.field.arg_name, ctx=ast.Load()),
                    args=[],
                    keywords={},
                )

            case pt.MaybeValue():
                return ast.Assign(
                    targets=[
                        ast.Tuple(
                            elts=[
                                ast.Name(id="val", ctx=ast.Store()),
                                ast.Name(id="exists", ctx=ast.Store()),
                            ],
                            ctx=ast.Store(),
                        )
                    ],
                    value=ast.Call(
                        func=ast.Name(id=e.op.name, ctx=ast.Load()),
                        args=[self._translate_ast(ex) for ex in e.args],
                        keywords={},
                    ),
                    lineno=0,
                )

            case pt.Return():
                return ast.Return(value=self._translate_ast(e.value))
            case pt.abi.MethodReturn():
                return ast.Return(value=self._translate_ast(e.arg))
            case ExitProgram():
                return ast.Return(value=self._translate_ast(e.success))

            case pt.abi.BaseType():
                return ast.Name(id="TODO", ctx=ast.Load())

            case pt.Int():
                return ast.Constant(value=e.value)
            case pt.Bytes():
                return ast.Constant(value=eval(e.byte_str))
            case str() | int():
                return ast.Constant(value=e)
            case bkr.state.ApplicationStateValue():
                return self._translate_ast(pt.App.globalGet(e.key))

            case _:
                print(dir(e))
                raise Unsupported(str(e.__class__))

            # case pt.ScratchSlot():
            #    nested_args.append(self._translate_ast(e.id))
            # case pt.ScratchStackStore():
            #    if e.slot is not None:
            #        nested_args.append(self._translate_ast(e.slot))

            # case pt.Bytes():
            #    nested_args.append(
            #        self._translate_ast(e.byte_str.replace('"', ""))
            #    )
            # case pt.Global():
            #    field = str(e.field).split(".")[1]
            #    name = "Global." + field
            # case pt.MultiValue():
            #    if len(e.immediate_args) > 0:
            #        nested_args.append(self._translate_ast(e.immediate_args))
            #    for arg in e.args:
            #        nested_args.append(self._translate_ast(arg))
            #    for os in e.output_slots:
            #        nested_args.append(self._translate_ast(os))
            #    if e.op.name == "app_local_get_ex":
            #        name = "App.localGetEx"
            #    elif e.op.name == "app_global_get_ex":
            #        name = "App.globalGetEx"

            # case pt.CommentExpr():
            #    name="Comment"
            #    #nested_args.append(e.comment)

    def _translate_op(self, op: pt.Op, type: pt.TealType) -> ast.AST:
        # TODO: currently only ints
        match op:
            case pt.Op.logic_and:
                return ast.And()
            case pt.Op.logic_or:
                return ast.Or()
            case pt.Op.logic_not:
                return ast.Not()
            case pt.Op.mul:
                return ast.Mult()
            case pt.Op.div:
                return ast.FloorDiv()
            case pt.Op.add:
                return ast.Add()
            case pt.Op.minus:
                return ast.Sub()
            case pt.Op.mod:
                return ast.Mod()
            case pt.Op.exp:
                return ast.Pow()
            case pt.Op.eq:
                return ast.Eq()
            case pt.Op.neq:
                return ast.NotEq()
            case pt.Op.gt:
                return ast.Gt()
            case pt.Op.ge:
                return ast.GtE()
            case pt.Op.lt:
                return ast.Lt()
            case pt.Op.le:
                return ast.LtE()
            case pt.Op.bitwise_or:
                return ast.BitOr()
            case pt.Op.bitwise_and:
                return ast.BitAnd()
            case pt.Op.bitwise_xor:
                return ast.BitXor()
            case pt.Op.shr:
                return ast.RShift()
            case pt.Op.shl:
                return ast.LShift()
            case pt.Op.getbyte:
                raise Unsupported("Cant get byte as an op")
            case pt.Op.len:
                raise Unsupported("Cant len stuff as an op")
            case pt.Op.pop:
                raise Unsupported("Cant pop stuff in python :thinking_face:")
            case _:
                raise Unsupported("Unsupported op: ", str(op))
