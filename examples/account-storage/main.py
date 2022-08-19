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


class TmplStruct(abi.NamedTuple):
    nonce: abi.Field[abi.String]
    inty: abi.Field[abi.Uint64]
    noncer: abi.Field[abi.String]
    interoo: abi.Field[abi.Uint64]


class DiskHungry(Application):

    blob_space = DynamicAccountStateValue(TealType.bytes, max_keys=16)

    tmpl_acct = Precompile(KeySig(version=6))

    @external
    def add_account(self, fields: TmplStruct, *, output: abi.DynamicArray[abi.Byte]):
        return Seq(
            (nonce := abi.String()).set(fields.nonce),
            (inty := abi.Uint64()).set(fields.inty),
            (noncer := abi.String()).set(fields.noncer),
            (interoo := abi.Uint64()).set(fields.interoo),
            (s := abi.String()).set(
                self.tmpl_acct.template_address(
                    nonce.get(), inty.get(), noncer.get(), interoo.get()
                )
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
    sp.fee = 3 * consts.milli_algo
    atc.add_transaction(
        TransactionWithSigner(
            txn=PaymentTxn(acct.address, sp, acct.address, 0), signer=acct.signer
        )
    )

    tmpl_vals = {"nonce": "dead", "inty": 123, "noncer": "beef", "interoo": 222}

    app_client.add_method_call(atc, DiskHungry.add_account, fields=tmpl_vals)

    result = atc.execute(app_client.client, 4)
    print(result.abi_results[0].return_value)

    dh = cast(DiskHungry, app_client.app)
    ta = dh.tmpl_acct
    # print(list(ta.binary))
    vals = list(tmpl_vals.values())
    # print(vals)
    print(list(ta.populate_template(*vals)))
    # print(ta.template_signer(b"dead", 123).lsig.address())

    # print(tmpl_signer.lsig.address())
    # app_client.call(DiskHungry.add_account, "blah")

    # bin, addr, map = app_client.compile(ta.teal(), True)
    # ta.set_compiled(bin, addr, map)
    # print(ta.__dict__)
    # print(ta.template_address(Bytes("asdf")))

    # app_client.build()


if __name__ == "__main__":
    demo()
