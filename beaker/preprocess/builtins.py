import pyteal as pt

## Types

BuiltInTypes: dict[str, pt.abi.BaseType] = {
    "int": pt.abi.Uint64,
    "str": pt.abi.String,
    "bytes": pt.abi.DynamicBytes,
}

## Functions


def _range(iters: pt.Expr) -> callable:
    def _impl(sv: pt.ScratchVar) -> tuple[pt.Expr, pt.Expr, pt.Expr]:
        return (sv.store(pt.Int(0)), sv.load() < iters, sv.store(sv.load() + pt.Int(1)))

    return _impl


def app_get(key: pt.Expr) -> pt.Expr:
    return pt.App.globalGet(key)


def app_get_ex(app_id: pt.Expr, key: pt.Expr) -> pt.Expr:
    return pt.App.globalGetEx(app_id, key)


def app_put(key: pt.Expr, val: pt.Expr) -> pt.Expr:
    return pt.App.globalPut(key, val)


def app_del(key: pt.Expr) -> pt.Expr:
    return pt.App.globalDel(key)


BuiltInFuncs: dict[str, callable] = {
    "range": _range,
    "app_get": app_get,
    "app_get_ex": app_get_ex,
    "app_put": app_put,
    "app_del": app_del,
}
