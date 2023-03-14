import pyteal as pt

import beaker

from examples.nested_precompile.smart_contracts import parent

app = beaker.Application("Grandparent")


@app.external
def create_parent(*, output: pt.abi.Uint64) -> pt.Expr:
    """Create a new parent app."""
    parent_pc = beaker.precompiled(parent.app)
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(parent_pc.get_create_config()),
        output.set(pt.InnerTxn.created_application_id()),
    )
