from app_handlers import calculator_app  # type: ignore

# example: APP_CLIENT_INIT
from beaker import client, sandbox

# grab funded accounts from the sandbox KMD
accts = sandbox.get_accounts()

# get a client for the sandbox algod
algod_client = sandbox.get_algod_client()

# create an application client for the calculator app
app_client = client.ApplicationClient(
    algod_client, calculator_app, signer=accts[0].signer
)
# example: APP_CLIENT_INIT


# example: APP_CLIENT_DEPLOY
app_id, app_addr, txid = app_client.create()
print(f"Created app with id: {app_id} and address: {app_addr} in tx: {txid}")
# example: APP_CLIENT_DEPLOY


# example: APP_CLIENT_CALL
result = app_client.call("add", a=1, b=2)
print(result.return_value)  # 3
# example: APP_CLIENT_CALL
