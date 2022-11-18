import pyteal as pt
from typing import Callable

# Type aliases for vars/values
VariableType = pt.ScratchVar | pt.abi.BaseType | pt.Expr
ValueType = pt.abi.TypeSpec | pt.TealType | None

# ABI type aliases
u64 = int
u32 = int
u16 = int
u8 = int
byte = int
string = str

# Stack type aliases
void = None
i = int
b = bytes
bigint = bytes


# Things we can translate from annotations
BuiltInTypes: dict[str, tuple[ValueType, type]] = {
    # Stack types
    "void": (pt.TealType.none, None),
    "i": (pt.TealType.uint64, int),
    "b": (pt.TealType.bytes, bytes),
    "bigint": (pt.TealType.bytes, int),
    # shorthand abi types
    "u64": (pt.abi.Uint64TypeSpec, int),
    "u32": (pt.abi.Uint32TypeSpec, int),
    "u16": (pt.abi.Uint16TypeSpec, int),
    "u8": (pt.abi.Uint8TypeSpec, int),
    "byte": (pt.abi.ByteTypeSpec, int),
    "string": (pt.abi.StringTypeSpec, str),
    # Python types
    "int": (pt.TealType.uint64, int),
    "str": (pt.TealType.bytes, str),
    "bytes": (pt.TealType.bytes, bytes),
    # compound types
    "list": (pt.abi.DynamicArrayTypeSpec, list),
    "tuple": (pt.abi.TupleTypeSpec, tuple),
}


# Functions
def _range(iters: pt.Expr) -> Callable:
    def _impl(sv: pt.ScratchVar) -> tuple[pt.Expr, pt.Expr, pt.Expr]:
        return (sv.store(pt.Int(0)), sv.load() < iters, sv.store(sv.load() + pt.Int(1)))

    return _impl


def _len(i: pt.Expr) -> pt.Expr:
    return pt.Len(i)


def log(msg: pt.Expr) -> pt.Expr:
    if msg.type_of() is pt.TealType.uint64:
        return pt.Log(pt.Itob(msg))
    return pt.Log(msg)


def concat(l: pt.Expr, *r: pt.Expr) -> pt.Expr:
    return pt.Concat(l, *r)


def app_get(key: pt.Expr) -> pt.Expr:
    return pt.App.globalGet(key)


def app_get_ex(app_id: pt.Expr, key: pt.Expr) -> pt.Expr:
    return pt.App.globalGetEx(app_id, key)


def app_put(key: pt.Expr, val: pt.Expr) -> pt.Expr:
    return pt.App.globalPut(key, val)


def app_del(key: pt.Expr) -> pt.Expr:
    return pt.App.globalDel(key)


BuiltInFuncs: dict[str, Callable] = {
    # python
    "len": _len,
    "range": _range,
    # avm
    "app_get": app_get,
    "app_get_ex": app_get_ex,
    "app_put": app_put,
    "app_del": app_del,
    "concat": concat,
    "log": log,
}
