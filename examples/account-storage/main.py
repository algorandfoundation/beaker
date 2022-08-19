from typing import cast
from algosdk.future.transaction import PaymentTxn
from algosdk.atomic_transaction_composer import *
from pyteal import *
from beaker import *
from beaker.consts import AppCallBudget

if __name__ == "__main__":
    from lsig import KeySig
else:
    from .lsig import KeySig


class DiskHungry(Application):

    blob_space = DynamicAccountStateValue(TealType.bytes, max_keys=16)

    tmpl_acct = Precompile(KeySig(version=6))

    @external
    def add_account(self, nonce: abi.DynamicArray[abi.Byte], *, output: abi.Address):
        return output.set(
            self.tmpl_acct.template_address(Suffix(nonce.encode(), Int(2)))
        )

    @external
    def populate_contract(
        self, nonce: abi.DynamicArray[abi.Byte], *, output: abi.DynamicArray[abi.Byte]
    ):
        return Seq(
            (s := abi.String()).set(
                self.tmpl_acct.populate_template_expr(Suffix(nonce.encode(), Int(2)))
            ),
            output.decode(s.encode()),
        )


def demo():
    acct = sandbox.get_accounts().pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), DiskHungry(), signer=acct.signer
    )
    # app_client.build()

    app_client.create()

    atc = AtomicTransactionComposer()
    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 2 * consts.milli_algo
    atc.add_transaction(
        TransactionWithSigner(
            txn=PaymentTxn(acct.address, sp, acct.address, 0), signer=acct.signer
        )
    )

    # tmpl_vals = {"nonce": "dead", "inty": 123, "noncer": "beef", "interoo": 222}

    app_client.add_method_call(atc, DiskHungry.add_account, nonce=b"dead")
    # app_client.add_method_call(atc, DiskHungry.populate_contract, nonce=b"dead")

    result = atc.execute(app_client.client, 4)
    print(result.abi_results[0].return_value)

    dh = cast(DiskHungry, app_client.app)
    ta = dh.tmpl_acct
    # print(list(ta.populate_template(b"dead")))
    print(ta.template_signer(b"dead").lsig.address())

    print(app_client.app.approval_program)

    # print(tmpl_signer.lsig.address())
    # app_client.call(DiskHungry.add_account, "blah")

    # bin, addr, map = app_client.compile(ta.teal(), True)
    # ta.set_compiled(bin, addr, map)
    # print(ta.__dict__)
    # print(ta.template_address(Bytes("asdf")))

    # app_client.build()


if __name__ == "__main__":
    demo()
