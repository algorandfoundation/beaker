import pyteal as pt
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)

import beaker

app_a = beaker.Application("A")


@app_a.external
def meth1(ptxn: pt.abi.PaymentTransaction, *, output: pt.abi.Uint64) -> pt.Expr:
    return output.set(ptxn.get().amount())


app_b = beaker.Application("B")


@app_b.external
def meth2(
    app: pt.abi.Application, method_1_txn: pt.abi.ApplicationCallTransaction
) -> pt.Expr:
    return pt.Approve()


def main() -> None:
    acct = beaker.sandbox.get_accounts().pop()
    algod = beaker.sandbox.get_algod_client()
    app_a_client = beaker.client.ApplicationClient(algod, app_a, signer=acct.signer)
    app_a_client.create()

    app_b_client = beaker.client.ApplicationClient(algod, app_b, signer=acct.signer)
    app_b_client.create()

    def works_but_weird() -> None:
        atc = AtomicTransactionComposer()
        atc = app_a_client.add_method_call(
            atc,
            meth1,
            ptxn=TransactionWithSigner(
                txn=transaction.PaymentTxn(
                    sender=acct.address,
                    amt=1000000,
                    receiver=app_a_client.app_addr,
                    sp=algod.suggested_params(),
                ),
                signer=acct.signer,
            ),
        )

        other_atc = AtomicTransactionComposer()
        other_atc.add_transaction(atc.txn_list[0])
        result = app_b_client.call(
            meth2, app=app_a_client.app_id, method_1_txn=atc.txn_list[1], atc=other_atc
        )
        print(result.tx_info)

    def works_but_sad() -> None:
        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                transaction.PaymentTxn(
                    acct.address,
                    algod.suggested_params(),
                    app_a_client.app_addr,
                    1000000,
                ),
                acct.signer,
            )
        )

        atc = app_b_client.add_method_call(
            atc,
            meth2,
            app=app_a_client.app_id,
            method_1_txn=TransactionWithSigner(
                transaction.ApplicationCallTxn(
                    acct.address,
                    algod.suggested_params(),
                    app_a_client.app_id,
                    on_complete=transaction.OnComplete.NoOpOC,
                    # hardcode reference to paytxn as second argument
                    app_args=[
                        meth1.method_spec().get_selector(),
                        (0).to_bytes(1, "big"),
                    ],
                ),
                acct.signer,
            ),
        )
        result = atc.execute(algod, 4)
        print(result)

    works_but_weird()
    # works_but_sad()


if __name__ == "__main__":
    main()
