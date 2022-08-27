import random
import string
from typing import cast
import algosdk.future.transaction as txns
from algosdk.atomic_transaction_composer import *
from pyteal import *
from beaker import *
from beaker.lib.storage import LocalBlob

# Simple logic sig, will approve _any_ transaction
# Used to expand our apps available state by
# creating unique account that will do whatever we need.
# In this case, we need it to opt in and rekey to the app address
class KeySig(LogicSignature):
    nonce = TemplateValue(TealType.bytes)
    def evaluate(self):
        return Approve() 


# App that needs lots of storage so we use the local storage of
# unique lsig accounts that have been rekeyed to the app address.
# This allows us to use the local storage of the unique accounts
# to get an extra 2k of storage for each account
class DiskHungry(Application):
    # Reserve 16 byte keys in local state
    stuff = DynamicAccountStateValue(TealType.bytes, max_keys=16)

    # Create a LocalBlob to be used for arbitrary read/writes of the 127*16 bytes avail
    blob = LocalBlob()

    # Signal to beaker that this should be compiled
    # prior to compiling the main application
    tmpl_acct = Precompile(KeySig(version=6))

    # Add account during opt in  by checking the sender against the address
    # we expect given the precompile && nonce
    @external(method_config=MethodConfig(opt_in=CallConfig.CALL))
    def add_account(self, nonce: abi.DynamicBytes):
        return Seq(
            Assert(
                # Make sure the opt-in'er is our lsig
                # Compute the expected sender given the precompile `tmpl_account` and the nonce
                Txn.sender() == self.tmpl_acct.template_address(nonce.get()),
                # and that its being rekeyed to us
                Txn.rekey_to() == self.address,
            ),
            # Zero out the local storage
            self.blob.zero(Txn.sender()),
        )


def demo():
    acct = sandbox.get_accounts().pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), DiskHungry(), signer=acct.signer
    )
    # Create the app
    app_client.create()

    # Create 10 random nonces for unique lsig accounts
    # and make them opt in to the app
    tmpl_lsig = cast(DiskHungry, app_client.app).tmpl_acct
    for _ in range(10):
        create_account(app_client, tmpl_lsig, get_nonce())


def get_nonce(n: int = 10) -> bytes:
    return ("".join(random.choice(string.ascii_uppercase) for _ in range(n))).encode()


def create_account(
    app_client: client.ApplicationClient, lsig_precompile: Precompile, nonce: bytes
):
    lsig_signer = lsig_precompile.template_signer(nonce)
    lsig_client = app_client.prepare(signer=lsig_signer)

    print(
        f"Creating templated lsig with nonce {nonce} and address {lsig_signer.lsig.address()}"
    )

    atc = AtomicTransactionComposer()

    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 2 * consts.milli_algo
    atc.add_transaction(
        TransactionWithSigner(
            txn=txns.PaymentTxn(
                # Give the lsig 1 algo for min balance (really less than that needed but I'm lazy)
                # TODO: get min bal reqs for optin from app?
                app_client.get_sender(),
                sp,
                lsig_signer.lsig.address(),
                consts.algo,
            ),
            signer=app_client.signer,
        )
    )

    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 0
    lsig_client.add_method_call(
        atc,
        DiskHungry.add_account,
        nonce=nonce,
        suggested_params=sp,
        rekey_to=app_client.app_addr,
        on_complete=txns.OnComplete.OptInOC,
    )

    atc.execute(app_client.client, 4)
    print("Done, current local state:")
    for k, v in lsig_client.get_account_state(raw=True).items():
        print(f"\t{k}\t: {len(v)} bytes")
    print()


if __name__ == "__main__":
    demo()
