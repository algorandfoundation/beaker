import pyteal as pt

import beaker

# Simple logic sig, will approve _any_ transaction
# Used to expand our apps available state by
# creating unique account that will do whatever we need.
# In this case, we need it to opt in and rekey to the app address
key_sig = beaker.LogicSignatureTemplate(
    pt.Approve(),
    runtime_template_variables={"nonce": pt.TealType.bytes},
    build_options=beaker.BuildOptions(avm_version=8),
)

# App that needs lots of storage so we use the local storage of
# unique lsig accounts that have been rekeyed to the app address.
# This allows us to use the local storage of the unique accounts
# to get an extra 2k of storage for each account
class DiskHungryState:
    # Reserve all 16 keys for the blob in local state
    data = beaker.LocalStateBlob(keys=16)


app = beaker.Application(
    "DiskHungry",
    build_options=beaker.BuildOptions(avm_version=8),
    state=DiskHungryState(),
)


# Add account during opt in  by checking the sender against the address
# we expect given the precompile && nonce
@app.opt_in
def add_account(nonce: pt.abi.DynamicBytes) -> pt.Expr:
    # Signal that this should be compiled
    # prior to compiling the main application
    tmpl_acct = beaker.precompiled(key_sig)

    return pt.Seq(
        pt.Assert(
            # Make sure the opt-in'er is our lsig
            pt.Txn.sender() == tmpl_acct.address(nonce=nonce.get()),
            # and that its being rekeyed to us
            pt.Txn.rekey_to() == pt.Global.current_application_address(),
        ),
        app.initialize_local_state(),
    )


@app.external
def flip_bit(nonce_acct: pt.abi.Account, bit_idx: pt.abi.Uint32) -> pt.Expr:
    """
    Allows caller to flip a bit at a given index for some
    account that has already opted in
    """

    return pt.Seq(
        # Read byte
        (byte := pt.ScratchVar()).store(
            app.state.data[nonce_acct.address()].read_byte(byte_idx(bit_idx.get()))
        ),
        # Flip bit
        byte.store(
            pt.SetBit(
                byte.load(),
                bit_in_byte_idx(bit_idx.get()),
                pt.Not(pt.GetBit(byte.load(), bit_in_byte_idx(bit_idx.get()))),
            )
        ),
        # Write byte
        app.state.data[nonce_acct.address()].write_byte(
            byte_idx(bit_idx.get()), byte.load()
        ),
    )


# no decorator, these are inlined
def byte_idx(bit_idx: pt.Expr) -> pt.Int:
    return bit_idx / pt.Int(8)


def bit_in_byte_idx(bit_idx: pt.Expr) -> pt.Int:
    return bit_idx % pt.Int(8)
