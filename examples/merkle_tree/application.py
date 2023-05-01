import pyteal as pt

import beaker

import examples.merkle_tree.merkle as mk


class MerkleTreeState:
    root = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes, default=mk.calc_init_root()
    )
    size = beaker.GlobalStateValue(stack_type=pt.TealType.uint64)


app = beaker.Application("MerkleTree", state=MerkleTreeState())


@app.delete(authorize=beaker.Authorize.only(pt.Global.creator_address()))
def delete() -> pt.Expr:
    return pt.Approve()


@app.create
def create() -> pt.Expr:
    return app.initialize_global_state()


@app.external
def verify_leaf(data: mk.Data, path: mk.Path) -> pt.Expr:
    """Calculate the expected root hash from the input
    and compare it to the actual stored root hash
    """
    return pt.Assert(app.state.root == mk.calc_root(pt.Sha256(data.get()), path))


@app.external
def append_leaf(data: mk.Data, path: mk.Path) -> pt.Expr:
    """Append a new leaf to the tree"""
    return pt.Seq(
        pt.Assert(
            # Since vacant leaves hold the hash of an empty string,
            # only non-empty strings are allowed to be appended
            data.encode() != pt.Bytes(""),
            # Make sure leaf is actually vacant by calculating the
            # root starting with an empty string
            app.state.root == mk.calc_root(pt.Sha256(pt.Bytes("")), path),
        ),
        # Calculate and update the new root
        app.state.root.set(mk.calc_root(pt.Sha256(data.get()), path)),
        # Increment the size
        app.state.size.increment(),
    )


@app.external
def update_leaf(old_data: mk.Data, new_data: mk.Data, path: mk.Path) -> pt.Expr:
    """Update the value of an existing leaf in the tree"""
    return pt.Seq(
        # Since vacant leaves hold the hash of an empty string,
        # only non-empty strings are allowed to be appended
        # Essentially this would be a 'delete' op, which we don't support currently
        pt.Assert(
            new_data.get() != pt.Bytes(""),
            # Verify the old value
            app.state.root == mk.calc_root(pt.Sha256(old_data.get()), path),
        ),
        # Calculate and update the new root
        app.state.root.set(mk.calc_root(pt.Sha256(new_data.get()), path)),
    )
