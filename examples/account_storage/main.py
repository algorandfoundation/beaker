import random
import string
from typing import cast
import algosdk.future.transaction as txns
import algosdk.atomic_transaction_composer
import pyteal
import beaker
from beaker.precompile import LSigTemplatePrecompile


# Simple logic sig, will approve _any_ transaction
# Used to expand our apps available state by
# creating unique account that will do whatever we need.
# In this case, we need it to opt in and rekey to the app address
def KeySig(version: int) -> beaker.LogicSignatureTemplate:
    return beaker.LogicSignatureTemplate(
        lambda: pyteal.Approve(),
        runtime_template_variables={"nonce": pyteal.TealType.bytes},
        teal_version=version,
    )


# App that needs lots of storage so we use the local storage of
# unique lsig accounts that have been rekeyed to the app address.
# This allows us to use the local storage of the unique accounts
# to get an extra 2k of storage for each account
class DiskHungry(beaker.Application):
    # Reserve all 16 keys for the blob in local state
    data = beaker.AccountStateBlob(keys=16)

    # Signal to beaker that this should be compiled
    # prior to compiling the main application
    tmpl_acct = LSigTemplatePrecompile(KeySig(version=6))

    # Add account during opt in  by checking the sender against the address
    # we expect given the precompile && nonce
    @beaker.opt_in
    def add_account(self, nonce: pyteal.abi.DynamicBytes):
        return pyteal.Seq(
            pyteal.Assert(
                # Make sure the opt-in'er is our lsig
                pyteal.Txn.sender()
                == self.tmpl_acct.logic.template_address(nonce=nonce.get()),
                # and that its being rekeyed to us
                pyteal.Txn.rekey_to() == self.address,
            ),
            self.initialize_account_state(),
        )

    # Inline these
    def byte_idx(self, bit_idx) -> pyteal.Int:
        return bit_idx / pyteal.Int(8)

    def bit_in_byte_idx(self, bit_idx) -> pyteal.Int:
        return bit_idx % pyteal.Int(8)

    @beaker.external
    def flip_bit(self, nonce_acct: pyteal.abi.Account, bit_idx: pyteal.abi.Uint32):
        """
        Allows caller to flip a bit at a given index for some account that has already opted in
        """

        return pyteal.Seq(
            # Read byte
            (byte := pyteal.ScratchVar()).store(
                self.data[nonce_acct.address()].read_byte(self.byte_idx(bit_idx.get()))
            ),
            # Flip bit
            byte.store(
                pyteal.SetBit(
                    byte.load(),
                    self.bit_in_byte_idx(bit_idx.get()),
                    pyteal.Not(
                        pyteal.GetBit(byte.load(), self.bit_in_byte_idx(bit_idx.get()))
                    ),
                )
            ),
            # Write byte
            self.data[nonce_acct.address()].write_byte(
                self.byte_idx(bit_idx.get()), byte.load()
            ),
        )


def demo():

    # Instantiate our app, since we're using a precompile we want this instance
    # to access the precompiled lsig
    app = DiskHungry()

    # Create app client
    app_client = beaker.client.ApplicationClient(
        client=beaker.sandbox.get_algod_client(),
        app=app,
        signer=beaker.sandbox.get_accounts().pop().signer,
    )

    # Deploy the app
    app_client.create()

    # Create 10 random nonces for unique lsig accounts
    # and make them opt in to the app
    for _ in range(10):
        # Populate the binary template with the random nonce and get back
        # a Signer obj to submit transactions
        nonce = get_nonce()
        lsig_signer = app.tmpl_acct.template_signer(nonce=nonce)

        print(
            f"Creating templated lsig with nonce {nonce} and address {lsig_signer.lsig.address()}"
        )

        # Create the account and opt it into the app, also rekeys it to the app address
        create_and_opt_in_account(
            app_client, app_client.prepare(signer=lsig_signer), nonce
        )

        # Max is 8 (bits per byte) * 127 (bytes per key) * 16 (max keys) == 16256
        idx = 16255
        app_client.call(
            DiskHungry.flip_bit, nonce_acct=lsig_signer.lsig.address(), bit_idx=idx
        )

        # Get the full state for the lsig we used to store this bit
        acct_state = app_client.get_account_state(lsig_signer.lsig.address(), raw=True)

        # Make sure the blob is in the right order
        blob = b"".join([acct_state[x.to_bytes(1, "big")] for x in range(16)])

        # Did the expected byte have the expected integer value?
        assert int(blob[idx // 8]) == 2 ** (idx % 8)
        print(f"bit set correctly at index {idx}")


def get_nonce(n: int = 10) -> bytes:
    return ("".join(random.choice(string.ascii_uppercase) for _ in range(n))).encode()


def create_and_opt_in_account(
    user_client: beaker.client.ApplicationClient,
    lsig_client: beaker.client.ApplicationClient,
    nonce: bytes,
):
    sp = user_client.get_suggested_params()
    lsig_address = cast(
        algosdk.atomic_transaction_composer.LogicSigTransactionSigner,
        lsig_client.signer,
    ).lsig.address()

    atc = algosdk.atomic_transaction_composer.AtomicTransactionComposer()

    # Give the lsig 2 algo for min balance (More than needed)
    user_client.add_transaction(
        atc,
        txns.PaymentTxn(
            sender=user_client.sender,
            sp=sp,
            receiver=lsig_address,
            amt=2 * beaker.consts.algo,
        ),
    )
    # Add opt in method call on behalf of lsig
    lsig_client.add_method_call(
        atc,
        DiskHungry.add_account,
        suggested_params=sp,
        nonce=nonce,
        rekey_to=lsig_client.app_addr,
        on_complete=txns.OnComplete.OptInOC,
    )

    # Run it
    atc.execute(user_client.client, 4)


if __name__ == "__main__":
    demo()
