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

    @external(method_config=MethodConfig(opt_in=CallConfig.CALL))
    def add_account(self, acct_name: abi.String):
        return Assert(
            Txn.sender() == self.tmpl_acct.template_address(acct_name.get()),
            Txn.rekey_to() == self.address,
        )


def demo():
    app_client = client.ApplicationClient(sandbox.get_algod_client(), DiskHungry())
    dh = cast(DiskHungry, app_client.app)
    ta = dh.tmpl_acct
    bin, addr, map = app_client.compile(ta.teal(), True)
    ta.set_compiled(bin, addr, map)
    print(ta.__dict__)
    print(ta.template_address(Bytes("asdf")))

    # app_client.build()


if __name__ == "__main__":
    demo()
