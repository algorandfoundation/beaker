import random
import string
from typing import cast

import algosdk.transaction as txns
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    LogicSigTransactionSigner,
)
from pyteal import (
    Approve,
    Assert,
    Expr,
    GetBit,
    Global,
    Int,
    Not,
    ScratchVar,
    Seq,
    SetBit,
    TealType,
    Txn,
    abi,
)

from beaker import (
    Application,
    BuildOptions,
    LocalStateBlob,
    LogicSignatureTemplate,
    client,
    consts,
    precompiled,
    sandbox,
    unconditional_create_approval,
)
from beaker.precompile import PrecompiledLogicSignatureTemplate

# Simple logic sig, will approve _any_ transaction
# Used to expand our apps available state by
# creating unique account that will do whatever we need.
# In this case, we need it to opt in and rekey to the app address
key_sig = LogicSignatureTemplate(
    Approve(),
    runtime_template_variables={"nonce": TealType.bytes},
    build_options=BuildOptions(avm_version=8),
)

# App that needs lots of storage so we use the local storage of
# unique lsig accounts that have been rekeyed to the app address.
# This allows us to use the local storage of the unique accounts
# to get an extra 2k of storage for each account
class DiskHungryState:
    # Reserve all 16 keys for the blob in local state
    data = LocalStateBlob(keys=16)


disk_hungry = Application(
    "DiskHungry",
    build_options=BuildOptions(avm_version=8),
    state=DiskHungryState(),
).implement(unconditional_create_approval)


# Add account during opt in  by checking the sender against the address
# we expect given the precompile && nonce
@disk_hungry.opt_in
def add_account(nonce: abi.DynamicBytes) -> Expr:
    # Signal to beaker that this should be compiled
    # prior to compiling the main application
    tmpl_acct = precompiled(key_sig)

    return Seq(
        Assert(
            # Make sure the opt-in'er is our lsig
            Txn.sender() == tmpl_acct.address(nonce=nonce.get()),
            # and that its being rekeyed to us
            Txn.rekey_to() == Global.current_application_address(),
        ),
        disk_hungry.initialize_local_state(),
    )


# Inline these
def byte_idx(bit_idx: Expr) -> Int:
    return bit_idx / Int(8)


def bit_in_byte_idx(bit_idx: Expr) -> Int:
    return bit_idx % Int(8)


@disk_hungry.external
def flip_bit(nonce_acct: abi.Account, bit_idx: abi.Uint32) -> Expr:
    """
    Allows caller to flip a bit at a given index for some
    account that has already opted in
    """

    return Seq(
        # Read byte
        (byte := ScratchVar()).store(
            disk_hungry.state.data[nonce_acct.address()].read_byte(
                byte_idx(bit_idx.get())
            )
        ),
        # Flip bit
        byte.store(
            SetBit(
                byte.load(),
                bit_in_byte_idx(bit_idx.get()),
                Not(GetBit(byte.load(), bit_in_byte_idx(bit_idx.get()))),
            )
        ),
        # Write byte
        disk_hungry.state.data[nonce_acct.address()].write_byte(
            byte_idx(bit_idx.get()), byte.load()
        ),
    )


def demo() -> None:
    # Create app client
    app_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=disk_hungry,
        signer=sandbox.get_accounts().pop().signer,
    )

    # Deploy the app
    app_client.create()

    # Create 10 random nonces for unique lsig accounts
    # and make them opt in to the app
    lsig_pc = PrecompiledLogicSignatureTemplate(key_sig, app_client.client)
    for _ in range(10):
        # Populate the binary template with the random nonce and get back
        # a Signer obj to submit transactions
        nonce = get_nonce()
        lsig_signer = LogicSigTransactionSigner(
            txns.LogicSigAccount(lsig_pc.populate_template(nonce=nonce))
        )

        print(
            f"Creating templated lsig with nonce {nonce} "
            + f"and address {lsig_signer.lsig.address()}"
        )

        # Create the account and opt it into the app, also rekeys it to the app address
        create_and_opt_in_account(
            app_client, app_client.prepare(signer=lsig_signer), nonce
        )

        # Max is 8 (bits per byte) * 127 (bytes per key) * 16 (max keys) == 16256
        idx: int = 16255
        app_client.call(flip_bit, nonce_acct=lsig_signer.lsig.address(), bit_idx=idx)

        # Get the full state for the lsig we used to store this bit
        acct_state = app_client.get_local_state(lsig_signer.lsig.address(), raw=True)

        # Make sure the blob is in the right order
        blob = b"".join(
            [cast(bytes, acct_state[x.to_bytes(1, "big")]) for x in range(16)]
        )

        # Did the expected byte have the expected integer value?
        assert int(blob[idx // 8]) == 2 ** (idx % 8)
        print(f"bit set correctly at index {idx}")


def get_nonce(n: int = 10) -> str:
    return "".join(random.choice(string.ascii_uppercase) for _ in range(n))


def create_and_opt_in_account(
    user_client: client.ApplicationClient,
    lsig_client: client.ApplicationClient,
    nonce: str,
) -> None:
    sp = user_client.get_suggested_params()
    lsig_address = cast(LogicSigTransactionSigner, lsig_client.signer).lsig.address()

    atc = AtomicTransactionComposer()

    # Give the lsig 2 algo for min balance (More than needed)
    user_client.add_transaction(
        atc,
        txns.PaymentTxn(
            sender=user_client.sender,
            sp=sp,
            receiver=lsig_address,
            amt=2 * consts.algo,
        ),
    )
    # Add opt in method call on behalf of lsig
    lsig_client.add_method_call(
        atc,
        "add_account",
        suggested_params=sp,
        nonce=nonce.encode(),
        rekey_to=lsig_client.app_addr,
        on_complete=txns.OnComplete.OptInOC,
    )

    # Run it
    atc.execute(user_client.client, 4)


if __name__ == "__main__":
    demo()
