import pyteal as pt

import beaker

lsig = beaker.LogicSignature(pt.Approve())

app = beaker.Application("Child2")


@app.external(read_only=True)
def get_lsig_addr(*, output: pt.abi.Address) -> pt.Expr:
    lsig_pc = beaker.precompiled(lsig)
    return output.set(lsig_pc.address())
