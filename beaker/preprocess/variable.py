import pyteal as pt
from ._builtins import VariableType, ValueType, BuiltInTypes


class Variable:
    def __init__(
        self, name: str, var: VariableType, value_type: ValueType, annotation: str
    ):
        self.name = name
        self.var = var
        self.value_type = value_type
        self.annotated_type = BuiltInTypes[annotation]

    def wrapped(
        self, e: pt.Expr, t: type[pt.abi.BaseType]
    ) -> tuple[pt.abi.BaseType, pt.Expr]:
        ts = pt.abi.type_spec_from_annotation(t)
        v = ts.new_instance()
        return (v, self.write(v, e))

    def write(self, val: pt.Expr) -> pt.Expr:
        match self.var:
            case pt.abi.String() | pt.abi.Address() | pt.abi.Uint() | pt.abi.DynamicBytes() | pt.abi.StaticBytes():
                return self.var.set(val)
            case pt.abi.BaseType():
                return self.var.decode(val)
            case pt.ScratchVar():
                return self.var.store(val)
            case _:
                raise Exception(f"Unsupported Var type: {type(self.var)}")

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
