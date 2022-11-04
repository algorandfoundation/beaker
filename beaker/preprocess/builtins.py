from pyteal import *


def _range(iters: Expr) -> callable:
    def _impl(sv: ScratchVar) -> tuple[Expr, Expr, Expr]:
        return (sv.store(Int(0)), sv.load() < iters, sv.store(sv.load() + Int(1)))

    return _impl


def app_get(key: Expr) -> Expr:
    return App.globalGet(key)


def app_get_ex(app_id: Expr, key: Expr) -> Expr:
    return App.globalGetEx(app_id, key)


def app_put(key: Expr, val: Expr) -> Expr:
    return App.globalPut(key, val)


def app_del(key: Expr) -> Expr:
    return App.globalDel(key)


BuiltIns: dict[str, callable] = {
    "range": _range,
    "app_get": app_get,
    "app_get_ex": app_get_ex,
    "app_put": app_put,
    "app_del": app_del,
}
