import pyteal as pt

import beaker

from examples.nested_precompile.smart_contracts import child1, child2

app = beaker.Application("Parent")


@app.external
def create_child_1(*, output: pt.abi.Uint64) -> pt.Expr:
    """Create a new child app."""
    child1_pc = beaker.precompiled(child1.app)
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(child1_pc.get_create_config()),
        output.set(pt.InnerTxn.created_application_id()),
    )


@app.external
def create_child_2(*, output: pt.abi.Uint64) -> pt.Expr:
    """Create a new child app."""
    child2_pc = beaker.precompiled(child2.app)
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(
            {
                **child2_pc.get_create_config(),
                pt.TxnField.global_num_uints: pt.Int(1),  # override because..?
            }
        ),
        output.set(pt.InnerTxn.created_application_id()),
    )
