from algosdk.future import transaction
from algosdk.atomic_transaction_composer import *
from application import Jackpot
from beaker import *


def demo():

    acct1 = sandbox.get_accounts().pop()
    acct2 = sandbox.get_accounts().pop()

    admin_app_client = client.ApplicationClient(
        sandbox.get_algod_client(), Jackpot(), signer=acct1.signer
    )

    app_id, app_addr, _ = admin_app_client.create()
    print(f"Created app with id {app_id} and address {app_addr}")

    player_app_client = admin_app_client.prepare(signer=acct2.signer)

    sp = player_app_client.client.suggested_params()

    result = player_app_client.opt_in(
        deposit=TransactionWithSigner(
            txn=transaction.PaymentTxn(acct2.address, sp, app_addr, 5 * consts.algo),
            signer=acct2.signer,
        )
    )
    print(result)

    result = admin_app_client.call(Jackpot.payout, winner=acct2.address)
    print(result)


if __name__ == "__main__":
    demo()
