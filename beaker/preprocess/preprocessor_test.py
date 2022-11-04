from pyteal import *
from beaker.application import Application
from beaker.decorators import external

from .preprocessor import Preprocessor
from .builtins import *


def test_parse_method():
   def meth():
       x = 3
       y = 2**2

       # Augmented assignment (load,op,store)
       x += 3
       x *= 3

       # Both mapped to truncated division
       x /= 3
       x //= 3

       z = "ok"

       while y > 0:
           y -= 1

       # `range` is a "builtin" we provide
       for _ in range(3):
           # maps to concat if the type is a string
           z += "no way"

       if x * y:
           return 1

       return x

   pp = Preprocessor(meth)
   print(pp.body)
   print(compileTeal(pp.body, mode=Mode.Application, version=8))


def test_built_ins():
   # TODO: all the others
   def meth():
       app_put("ok", 123)
       x = app_get("ok")
       app_del("ok")
       return x

   pp = Preprocessor(meth)
   print(pp.body)
   print(compileTeal(pp.body, mode=Mode.Application, version=8))


def test_app():
    class App(Application):
        @external(translate=True)
        def no_args_no_output(self):
           x = 2
           x += 3

        @external
        def no_args_yes_output_pt(self, *, output: abi.Uint64) -> Expr:
           return output.set(Int(2))


        @external(translate=True)
        def no_args_yes_output_py(self) -> int:
            return 2

    app = App()
    print(app.approval_program)
