from typing import cast
import algosdk.future.transaction as txns
from algosdk.atomic_transaction_composer import *
from pyteal import *
from beaker import *
from beaker.consts import AppCallBudget

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
            Assert(
                Txn.sender()
                == self.tmpl_acct.template_address(Suffix(nonce.encode(), Int(2)))
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
    for x in range(10):
        nonce = x.to_bytes(8, "big")

        lsig_signer = tmpl_acct.template_signer(nonce)
        lsig_client = app_client.prepare(signer=lsig_signer)

        atc = AtomicTransactionComposer()

        sp = app_client.get_suggested_params()
        sp.flat_fee = True
        sp.fee = 2 * consts.milli_algo
        atc.add_transaction(
            TransactionWithSigner(
                txn=txns.PaymentTxn(
                    acct.address, sp, lsig_signer.lsig.address(), consts.algo
                ),
                signer=acct.signer,
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
            on_complete=txns.OnComplete.OptInOC,
        )

        atc.execute(app_client.client, 4)

        print(lsig_client.get_account_state())


if __name__ == "__main__":
    demo()
