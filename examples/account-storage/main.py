import random
import string
from typing import cast
import algosdk.future.transaction as txns
from algosdk.atomic_transaction_composer import *
from pyteal import *
from beaker import *

if __name__ == "__main__":
    from lsig import KeySig
else:
    from .lsig import KeySig


class DiskHungry(Application):
    stuff = AccountStateValue(TealType.bytes, default=Bytes("lol"))

    tmpl_acct = Precompile(KeySig(version=6))

    @external(method_config=MethodConfig(opt_in=CallConfig.CALL))
    def add_account(self, nonce: abi.DynamicArray[abi.Byte]):
        return Seq(
            (expected_sender := ScratchVar()).store(
                self.tmpl_acct.template_address(Suffix(nonce.encode(), Int(2)))
            ),
            Assert(
                Txn.sender() == expected_sender.load(),
                Txn.rekey_to() == self.address,
            ),
            self.initialize_account_state(),
        )


def demo():
    acct = sandbox.get_accounts().pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), DiskHungry(), signer=acct.signer
    )
    app_client.create()

    tmpl_acct = cast(DiskHungry, app_client.app).tmpl_acct
    for _ in range(10):
        create_account(app_client, tmpl_acct, get_nonce())


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
                app_client.get_sender(), sp, lsig_signer.lsig.address(), consts.algo
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

    print(f"Done, current local state: {lsig_client.get_account_state()}")


if __name__ == "__main__":
    demo()
