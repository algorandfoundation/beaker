# example: INIT_APP
from beaker import Application

app = Application("MyRadApp", descr="This is a rad app")
# example: INIT_APP

# example: APP_SPEC
app_spec = app.build()
print(app_spec.to_json())
# example: APP_SPEC


# example: HANDLERS_DIRECT
import pyteal as pt


# use the decorator provided on the `app` object to register a handler
@app.external
def add(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
    return output.set(a.get() + b.get())


# example: HANDLERS_DIRECT

# example: HANDLERS_BLUEPRINT
# passing the app to this method will register the handlers on the app
def calculator_blueprint(app: Application) -> Application:
    @app.external
    def add(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(a.get() + b.get())

    @app.external
    def sub(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(a.get() - b.get())

    @app.external
    def div(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(a.get() / b.get())

    @app.external
    def mul(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(a.get() * b.get())

    return app


calculator_app = Application("CalculatorApp", descr="This is a calculator app")
calculator_app.apply(calculator_blueprint)

calculator_app_spec = calculator_app.build()
print(calculator_app_spec.to_json())
# example: HANDLERS_BLUEPRINT
