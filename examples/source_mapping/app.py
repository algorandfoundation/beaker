import pyteal as pt

from beaker import Application, BuildOptions

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
def add(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
    return pt.Seq(
        pt.Assert(a.get() > pt.Int(10), comment="a must be > 10"),
        pt.Assert(b.get() < pt.Int(10), comment="b must be < 10"),
        output.set(a.get() + b.get()),
    )
