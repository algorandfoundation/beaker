from typing import cast
from pyteal import *
from beaker import *

if __name__ == "__main__":
    from lsig import KeySig
else:
    from .lsig import KeySig


class DiskHungry(Application):

    blob_space = DynamicAccountStateValue(TealType.bytes, max_keys=16)

    tmpl_acct = Precompile(KeySig(version=6))

    @external
    def add_account(self, acct_name: abi.String, *, output: abi.Address):
        return output.set(self.tmpl_acct.template_address(acct_name.get()))


def demo():
    acct = sandbox.get_accounts().pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), DiskHungry(), signer=acct.signer
    )
    app_client.build()

    # app_client.create()

    dh = cast(DiskHungry, app_client.app)
    ta = dh.tmpl_acct
    print(ta.populate_template(b"blah"))
    print(ta.template_signer(b"blah").lsig.address())

    # tmpl_signer = cast(DiskHungry, app_client.app).tmpl_acct.template_signer(b"blah")
    # print(tmpl_signer.lsig.address())
    # app_client.call(DiskHungry.add_account, "blah")

    # bin, addr, map = app_client.compile(ta.teal(), True)
    # ta.set_compiled(bin, addr, map)
    # print(ta.__dict__)
    # print(ta.template_address(Bytes("asdf")))

    # app_client.build()


if __name__ == "__main__":
    demo()
