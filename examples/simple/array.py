from typing import Literal
from pyteal import *
from beaker import *


class JasonsArrayExample(Application):

    data = ApplicationStateBlob(keys=2)

    @create
    def create(self):
        return Seq(
            self.initialize_application_state(),
            # Fill buffer first so we only write to the blob once
            (buf := ScratchVar()).store(Bytes("")),
            For(
                (i := ScratchVar()).store(Int(0)),
                i.load() < Int(16),
                i.store(i.load() + Int(1)),
            ).Do(buf.store(Concat(buf.load(), Itob(i.load())))),
            # Now do the write once (its expensive in ops)
            self.data.write(Int(0), buf.load()),
        )

    @external
    def gimme_static_array(self, *, output: abi.StaticArray[abi.Uint64, Literal[16]]):
        # A static array of static types needs no special treatment (use static if possible)
        return output.decode(self.data.read(Int(0), Int(8 * 16)))

    @external
    def gimme_dynamic_array(self, *, output: abi.DynamicArray[abi.Uint64]):
        # A dynamic array needs some finagling
        return output.decode(
            # Prepend the bytes with the length as a uint16, according to ABI spec
            Concat(Suffix(Itob(Int(16)), Int(6)), self.data.read(Int(0), Int(8 * 16)))
        )


if __name__ == "__main__":
    algod_client = sandbox.get_algod_client()
    acct = sandbox.get_accounts().pop()

    ac = client.ApplicationClient(
        algod_client, JasonsArrayExample(), signer=acct.signer
    )

    print("Creating App")
    ac.create()

    print("Getting the static array")
    result = ac.call(JasonsArrayExample.gimme_static_array)
    print(f"result: {result.return_value}")

    print("Getting the dynamic array")
    result = ac.call(JasonsArrayExample.gimme_dynamic_array)
    print(f"result: {result.return_value}")
