import pyteal as pt
import ast


# Note: Wrapping an ast node in `Expr(value=xxx)` pushes it to the next line


def Unsupported(*feature):
    return Exception(f"This feature is not supported yet: {' '.join(feature)}")


op_lookup = {str(op): op.name for op in pt.Op}


class Unprocessor:
    def __init__(self, e: pt.Expr):
        self.slots_in_use: dict[int, pt.ScratchSlot] = {}
        self.native_ast = ast.fix_missing_locations(
            ast.Module(body=self._translate_ast(e, 0), type_ignores=[])
        )
        # self.source = ast.unparse(self.native_ast)

    def _translate_ast(self, e: pt.Expr, lineno: int = 0) -> ast.AST:
        match e:
            case pt.Seq():
                return [ast.Expr(value=self._translate_ast(expr)) for expr in e.args]
            case pt.Cond():
                conditions: list[ast.If] = []
                for arg in e.args:
                    test: ast.AST = self._translate_ast(arg[0])
                    body: ast.AST = ast.Expr(value=self._translate_ast(arg[1]))
                    conditions.append(ast.If(test=test, body=body, orelse=[]))

                conditions[0].orelse = conditions[1:]
                return conditions[0]

            case pt.If():
                test: ast.AST = self._translate_ast(e.cond)
                body: ast.AST = ast.Expr(value=self._translate_ast(e.thenBranch))
                orelse: list[ast.AST] = []
                if e.elseBranch is not None:
                    orelse.append(self._translate_ast(e.elseBranch))
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
                    test = ast.BinOp(
                        left=test, right=self._translate_ast(cond), op=ast.And()
                    )
                return ast.Assert(test=test)

            case pt.SubroutineCall():
                fn_name: str = e.subroutine.implementation.__name__
                call_args: list[ast.AST] = [self._translate_ast(a) for a in e.args]
                return ast.Call(
                    func=ast.Name(id=fn_name, ctx=ast.Load()),
                    args=call_args,
                    keywords={},
                )

            case pt.Int():
                return ast.Constant(value=e.value)

            case pt.TxnExpr():
                return ast.Call(
                    func=ast.Name(id=f"txn_{e.field.name}", ctx=ast.Load()),
                    args=[],
                    keywords={},
                )

            case _:
                print(dir(e))
                raise Unsupported(str(e.__class__))

            # case pt.BinaryExpr():
            #    nested_args.append(self._translate_ast(e.argLeft))
            #    nested_args.append(self._translate_ast(e.argRight))
            # case pt.App():
            #    field = str(e.field).split(".")[1]
            #    name = "App." + field
            #    for arg in e.args:
            #        nested_args.append(self._translate_ast(arg))
            # case pt.Bytes():
            #    nested_args.append(
            #        self._translate_ast(e.byte_str.replace('"', ""))
            #    )
            # case pt.UnaryExpr():
            #    nested_args.append(self._translate_ast(e.arg))
            # case pt.TxnaExpr():
            #    field = str(e.field).split(".")[1]
            #    name = f"Txna.{field}"
            #    nested_args.append(self._translate_ast(e.index))
            # case pt.Return():
            #    nested_args.append(self._translate_ast(e.value))
            # case pt.If():
            #    nested_args.append(self._translate_ast(e.cond))
            #    nested_args.append(self._translate_ast(e.thenBranch))
            #    if e.elseBranch is not None:
            #        nested_args.append(self._translate_ast(e.elseBranch))
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

            # case pt.EnumInt():
            #    name = "OnComplete." + e.name
            # case pt.ScratchSlot():
            #    nested_args.append(self._translate_ast(e.id))
            # case pt.ScratchStackStore():
            #    if e.slot is not None:
            #        nested_args.append(self._translate_ast(e.slot))
            # case pt.ScratchLoad():
            #    if e.slot is not None:
            #        nested_args.append(self._translate_ast(e.slot))
            # case pt.ScratchStore():
            #    if e.slot is not None:
            #        nested_args.append(self._translate_ast(e.slot))
            #    nested_args.append(self._translate_ast(e.value))
            # case pt.ExitProgram():
            #    name = "ExitProgram"
            #    nested_args.append(self._translate_ast(e.success))
            # case pt.CommentExpr():
            #    name="Comment"
            #    #nested_args.append(e.comment)
            # case int() | str() | bytes():
            #    pass
            # case _:
            #    print(f"unhandled: {e.__class__}")
            #    pass

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
            case pt.Op.len:
                raise Unsupported("Cant len stuff as an op")
            case pt.Op.pop:
                raise Unsupported("Cant pop stuff in python :thinking_face:")
            case _:
                raise Unsupported("Unsupported op: ", str(op))
