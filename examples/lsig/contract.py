from Cryptodome.Hash import keccak
from pyteal import *
from beaker import *
from lsig import EthEcdsaVerify, HashValue, Signature


class EthChecker(Application):
    @external
    def check_eth_sig(
        self, hash: HashValue, signature: Signature, *, output: abi.String
    ):
        return Seq(
            x := App.globalGetEx(Int(0), Bytes("thekey")),
            Assert(x.hasValue()),
            Assert(
                Txn.sender()
                == Addr("SVRVGQFTQEX5PUNWK6BDACE63DGYWF2Z6CUCVBCJFPNJV7XI2DRHO2MW5M")
            ),
            output.set("lsig validated"),
        )


if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import (
        AtomicTransactionComposer,
        AccountTransactionSigner,
        LogicSigTransactionSigner,
        TransactionWithSigner,
    )
    from algosdk.future.transaction import *
    from beaker import sandbox, client, consts

    algod_client = sandbox.get_client()
    accts = sandbox.get_accounts()

    addr, sk = accts.pop()
    signer = AccountTransactionSigner(sk)
    app = EthChecker()

    app_client = client.ApplicationClient(algod_client, app, signer=signer)
    app_id, app_addr, txid = app_client.create()

    eev = EthEcdsaVerify()
    program, src_map = app_client.compile(eev.program, True)

    lsa = LogicSigAccount(program)
    lsig_signer = LogicSigTransactionSigner(lsa)
    lsig_client = app_client.prepare(signer=lsig_signer)

    atc = AtomicTransactionComposer()

    # Add a payment just to cover fees
    sp_with_fees = algod_client.suggested_params()
    sp_with_fees.flat_fee = True
    sp_with_fees.fee = consts.milli_algo * 3
    atc.add_transaction(
        TransactionWithSigner(
            txn=PaymentTxn(addr, sp_with_fees, addr, 0), signer=signer
        )
    )

    message = b"OpenZeppelin"
    m = keccak.new(digest_bits=256)
    m.update(message)
    hash = m.digest()

    sp_no_fee = algod_client.suggested_params()
    sp_no_fee.flat_fee = True
    # V0
    hex_signature = "5d99b6f7f6d1f73d1a26497f2b1c89b24c0993913f86e9a2d02cd69887d9c94f3c880358579d811b21dd1b7fd9bb01c1d81d10e69f0384e675c32b39643be8921b"
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        app.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    # V1
    hex_signature = "331fe75a821c982f9127538858900d87d3ec1f9f737338ad67cad133fa48feff48e6fa0c18abc62e42820f05943e47af3e9fbe306ce74d64094bdf1691ee53e01c"
    signature = bytes.fromhex(hex_signature)
    atc = lsig_client.add_method_call(
        atc,
        app.check_eth_sig,
        hash=hash,
        signature=signature,
        suggested_params=sp_no_fee,
    )

    result = atc.execute(algod_client, 4)
    for result in result.abi_results:
        print(result.return_value)
