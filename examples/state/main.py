from contract import StateExample
from beaker.client import ApplicationClient
from beaker.sandbox import get_algod_client, get_accounts

accts = get_accounts()

acct, sk, signer = accts.pop()

client = get_algod_client()

app = StateExample()
app_client = ApplicationClient(client, app, signer=signer)
app_id, app_address, transaction_id = app_client.create()
print(
    f"DEPLOYED: App ID: {app_id} Address: {app_address} Transaction ID: {transaction_id}"
)

app_client.opt_in()
print("Opted in")

app_client.call(app.set_account_state_val, v=123)
result = app_client.call(app.get_account_state_val)
print(f"Set/get acct state result: {result.return_value}")


app_client.call(app.set_dynamic_account_state_val, k=0, v="stuff")
result = app_client.call(app.get_dynamic_account_state_val, k=0)
print(f"Set/get dynamic acct state result: {result.return_value}")

try:
    app_client.call(app.set_app_state_val, v="Expect fail")
except Exception:
    print("Task failed successfully")
    result = app_client.call(app.get_app_state_val)
    print(f"Set/get app state result: {result.return_value}")


app_client.call(app.set_dynamic_app_state_val, k=15, v=123)
result = app_client.call(app.get_dynamic_app_state_val, k=15)
print(f"Set/get dynamic app state result: {result.return_value}")
