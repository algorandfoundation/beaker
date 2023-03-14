import pyteal as pt

import beaker


class State:
    manager = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes, default=pt.Global.creator_address()
    )

    nickname = beaker.LocalStateValue(
        stack_type=pt.TealType.bytes, descr="what this user prefers to be called"
    )


app = (
    beaker.Application("Nicknames", state=State())
    .apply(beaker.unconditional_create_approval, initialize_global_state=True)
    .apply(beaker.unconditional_opt_in_approval, initialize_local_state=True)
)


@app.close_out(bare=True)
def close_out() -> pt.Expr:
    return pt.Approve()


@app.delete(bare=True, authorize=beaker.Authorize.only(app.state.manager))
def delete() -> pt.Expr:
    return pt.Approve()


@app.external(authorize=beaker.Authorize.only(app.state.manager))
def set_manager(new_manager: pt.abi.Address) -> pt.Expr:
    return app.state.manager.set(new_manager.get())


@app.external
def set_nick(nick: pt.abi.String) -> pt.Expr:
    return app.state.nickname.set(nick.get())


@app.external(read_only=True)
def get_nick(*, output: pt.abi.String) -> pt.Expr:
    return output.set(app.state.nickname)
