from pyteal import *
from beaker import *
from beaker.application import get_method_selector


class Testy(Application):
    """Testy has 2 ABI methods, one meant to be called from an outer and one from an inner transaction"""

    @handler
    def handle_outer(
        self, acct1: abi.Account, acct2: abi.Account, app: abi.Application
    ):
        # Use the new Execute method
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: app.application_id(),
                # Pass _all_ the accounts we got in the transaction
                # NOTE: requires the itxn-txna branch of pyteal
                TxnField.accounts: Txn.accounts,
                TxnField.application_args: [
                    Bytes(get_method_selector(self.handle_inner))
                ],
            }
        )

    @handler
    def handle_inner(self):
        return Assert(
            # I'm being called by another app
            Global.caller_app_id() > Int(0),
            # I got accounts passed
            Txn.accounts.length() > Int(0),
        )


if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import AccountTransactionSigner
    from beaker import sandbox, client, consts

    algod_client = sandbox.get_client()

    accts = sandbox.get_accounts()
    addr, sk = accts.pop()
    signer = AccountTransactionSigner(sk)

    addr1, _ = accts.pop()
    addr2, _ = accts.pop()

    # Create first app
    a1 = Testy()
    outer_client = client.ApplicationClient(algod_client, a1, signer=signer)
    outer_client.create()

    # Create second app
    a2 = Testy()
    inner_client = client.ApplicationClient(algod_client, a2, signer=signer)
    inner_client.create()

    # try to call second from first, note we did _not_ fund 
    # the first app but we're covering the transaction with suggested params
    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = 2 * consts.milli_algo
    result = outer_client.call(
        a1.handle_outer,
        suggested_params=sp,
        acct1=addr1,
        acct2=addr2,
        app=inner_client.app_id,
    )
    print(f"Committed in: {result.tx_id}")
