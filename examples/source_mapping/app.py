from feature_gates import FeatureGates  # type: ignore[import]

FeatureGates.set_sourcemap_enabled(True)  # noqa: FBT003

# Import pyteal _after_ setting feature gate option
from pyteal import Assert, Expr, Int, Seq, abi  # noqa: E402

from beaker import Application, BuildOptions, client, sandbox  # noqa: E402

# Set up our build options to enable source mapping
# of pyteal program
source_mapped_app = Application(
    "SourceMapped",
    build_options=BuildOptions(
        with_sourcemaps=True,
        annotate_teal=True,
        annotate_teal_headers=True,
        annotate_teal_concise=False,
    ),
)


@source_mapped_app.external
def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
    return Seq(
        Assert(a.get() > Int(10), comment="a must be > 10"),
        Assert(b.get() < Int(10), comment="b must be < 10"),
        output.set(a.get() + b.get()),
    )


def demo() -> None:
    ac = sandbox.get_algod_client()
    acct = sandbox.get_accounts().pop()

    app_spec = source_mapped_app.build(ac)
    write_programs(app_spec.approval_program, app_spec.clear_program)

    app_client = client.ApplicationClient(client=ac, app=app_spec, signer=acct.signer)
    # deploy app
    app_client.create()

    # trigger assert
    app_client.call(add, a=12, b=42)


def write_programs(approval: str, clear: str) -> None:
    with open("approval.teal", "w") as f:
        f.write(approval)

    with open("clear.teal", "w") as f:
        f.write(clear)


if __name__ == "__main__":
    demo()
