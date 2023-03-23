# example: BEAKER_INIT_APP
from beaker import Application

app = Application("MyRadApp", descr="This is a rad app")
# example: BEAKER_INIT_APP

# example: BEAKER_APP_SPEC
app_spec = app.build()
print(app_spec.to_json())
# example: BEAKER_APP_SPEC
