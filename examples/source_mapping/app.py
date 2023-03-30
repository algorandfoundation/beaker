from feature_gates import FeatureGates  # type: ignore[import]

FeatureGates.set_sourcemap_enabled(True)  # noqa: FBT003

# Import pyteal _after_ setting feature gate option
from pyteal import Assert, Expr, Int, Seq, abi  # noqa: E402

from beaker import Application, BuildOptions  # noqa: E402

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
