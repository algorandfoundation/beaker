import pyteal as pt
from ._builtins import VariableType, ValueType, BuiltInTypes


class Variable:
    def __init__(
        self,
        name: str,
        var: VariableType,
        value_type: ValueType,
        annotation: str | None = None,
    ):
        self.name = name
        self.var = var
        self.value_type = value_type

        if annotation is not None:
            self.annotated_type = BuiltInTypes[annotation]

    @staticmethod
    def from_type(name: str, t: ValueType) -> "Variable":
        var: VariableType

        if t is None:
            var = pt.ScratchVar()
        else:
            if isinstance(t, pt.abi.TypeSpec):
                var = t.new_instance()
            else:
                var = pt.ScratchVar(t)
        return Variable(name, var, t)

    def get_scratch_var(self) -> pt.ScratchVar:
        match self.var:
            case pt.ScratchVar():
                return self.var
            case pt.abi.BaseType():
                if hasattr(self.var, "_stored_value"):
                    return self.var._stored_value  # type: ignore[attr-defined]
                else:
                    return self.var.stored_value  # type: ignore[attr-defined]
            case _:
                raise Exception(f"No scratch var associated with {self.name}")

    def stack_type(self) -> pt.TealType:
        return pt.TealType.uint64

    def wrapped(
        self, e: pt.Expr, t: type[pt.abi.BaseType]
    ) -> tuple[pt.abi.BaseType, pt.Expr]:
        ts = pt.abi.type_spec_from_annotation(t)
        v = ts.new_instance()
        return (v, self.write(v, e))

    def write(self, val: pt.Expr) -> pt.Expr:
        return write_into_var(self.var, val)

    def read(self) -> pt.Expr:
        match self.var:
            case pt.abi.String() | pt.abi.Address() | pt.abi.DynamicBytes() | pt.abi.StaticBytes() | pt.abi.Uint():
                return self.var.get()
            case pt.abi.BaseType():
                if hasattr(self.var, "_stored_value"):
                    return self.var._stored_value.load()  # type: ignore[attr-defined]
                else:
                    return self.var.stored_value.load()  # type: ignore[attr-defined]
            case pt.ScratchVar():
                return self.var.load()
            case _:
                raise Exception(f"Unsupported Var type: {type(self.var)}")


def write_into_var(var: VariableType, val: pt.Expr) -> pt.Expr:
    match var:
        case pt.abi.String() | pt.abi.Address() | pt.abi.Uint() | pt.abi.DynamicBytes() | pt.abi.StaticBytes():
            return var.set(val)
        case pt.abi.BaseType():
            return var.decode(val)
        case pt.ScratchVar():
            return var.store(val)
        case _:
            raise Exception(f"Unsupported Var type: {type(var)}")


def read_from_var(var: VariableType) -> pt.Expr:
    match var:
        case pt.abi.String() | pt.abi.Address() | pt.abi.DynamicBytes() | pt.abi.StaticBytes() | pt.abi.Uint():
            return var.get()
        case pt.abi.BaseType():
            if hasattr(var, "_stored_value"):
                return var._stored_value.load()  # type: ignore[attr-defined]
            else:
                return var.stored_value.load()  # type: ignore[attr-defined]
        case pt.ScratchVar():
            return var.load()
        case _:
            raise Exception(f"Unsupported Var type: {type(var)}")
