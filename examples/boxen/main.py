from pyteal import *
from beaker import *

class Boxen(Application):

    @external
    def make_box(self, name: abi.String, size: abi.Uint32):
        return Pop(BoxCreate(name.get(), size.get()))


if __name__ == "__main__":
    b = Boxen()
    print(b.application_spec())