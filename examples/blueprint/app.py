from pyteal import Expr, Int, Sqrt, abi

from beaker import Application


# A blueprint that adds a method named `add` to the external
# methods of the Application passed
def add_blueprint(app: Application) -> None:
    @app.external
    def add(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(a.get() + b.get())


app = Application("BlueprintExampleNoArgs").apply(add_blueprint)

# A blueprint that adds a method named `addN` to the external
# methods of the Application passed
def add_n_blueprint(app: Application, n: int) -> None:
    @app.external
    def add_n(a: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(a.get() + Int(n))


app = Application("BlueprintExampleWithArgs").apply(add_n_blueprint, n=1)


# A blueprint that adds a method named `div` to the external
# methods of the Application passed
def div_blueprint(app: Application) -> None:
    @app.external
    def div(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(a.get() / b.get())


# A blueprint that adds a method named `mul` to the external
# methods of the Application passed
def mul_blueprint(app: Application) -> None:
    @app.external
    def mul(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(a.get() * b.get())


# A blueprint that adds a method named `sub` to the external
# methods of the Application passed
def sub_blueprint(app: Application) -> None:
    @app.external
    def sub(a: abi.Uint64, b: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(a.get() - b.get())


def calculator_blueprint(app: Application) -> None:
    add_blueprint(app)
    sub_blueprint(app)
    div_blueprint(app)
    mul_blueprint(app)


def sqrt_blueprint(app: Application) -> None:
    @app.external
    def sqrt(a: abi.Uint64, *, output: abi.Uint64) -> Expr:
        return output.set(Sqrt(a.get()))


# create an instance of Application
extended_app = Application("ExtendAppWithBlueprints")
# include the handlers from our calculator blueprint
extended_app.apply(calculator_blueprint)
