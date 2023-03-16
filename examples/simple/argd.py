from pyteal import Expr, Len, abi

from beaker import Application, sandbox

x = Application("x")


@x.create
def create(a: abi.Uint64, b: abi.String, *, output: abi.Uint64) -> Expr:
    return output.set(a.get() + Len(b.get()))


if __name__ == "__main__":
    c = sandbox.get_algod_client()
    spec = x.build(c)
    print(spec.to_json())
