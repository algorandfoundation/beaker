from beaker.logic_signature import LogicSignature
from beaker.consts import Algos
from beaker.decorators import external
from pyteal import *


class MyLsig(LogicSignature):
    seeder: Addr

    def __init__(self, seed_addr: str):
        super().__init__()
        self.seeder = Addr(seed_addr)

    @external
    def seed(self):
        seed_payment, optin_asset, rcv_asset = Gtxn[0], Gtxn[1], Gtxn[2]
        return And(
            Global.group_size() == Int(3),
            # Seed with funds
            seed_payment.type_enum() == TxnType.Payment,
            seed_payment.sender() == self.seeder,
            seed_payment.amount() == Algos(0.3),
            seed_payment.close_remainder_to() == Global.zero_address(),
            # Opt escrow into asset
            optin_asset.type_enum() == TxnType.AssetTransfer,
            optin_asset.asset_amount() == Int(0),
            optin_asset.asset_receiver() == Gtxn[1].sender(),
            optin_asset.asset_receiver() == Gtxn[0].receiver(),
            # Xfer asset from creator to escrow
            rcv_asset.type_enum() == TxnType.AssetTransfer,
            rcv_asset.asset_amount() == Int(1),
            rcv_asset.asset_receiver() == Gtxn[0].receiver(),
            rcv_asset.sender() == Gtxn[0].sender(),
            rcv_asset.asset_close_to() == Global.zero_address(),
            rcv_asset.xfer_asset() == Gtxn[1].xfer_asset(),
        )

    @external
    def recover(self):
        cosign, close_asset, close_algos = Gtxn[0], Gtxn[1], Gtxn[2]
        return And(
            Global.group_size() == Int(3),
            # Make sure seeder cosigned
            cosign.type_enum() == TxnType.Payment,
            cosign.sender() == self.seeder,
            cosign.receiver() == self.seeder,
            cosign.amount() == Int(0),
            cosign.close_remainder_to() == Global.zero_address(),
            cosign.rekey_to() == Global.zero_address(),
            # Close out asset
            close_asset.type_enum() == TxnType.AssetTransfer,
            close_asset.asset_amount() == Int(0),
            close_asset.asset_close_to() == self.seeder,
            # Close out algos
            close_algos.type_enum() == TxnType.Payment,
            close_algos.amount() == Int(0),
            close_algos.close_remainder_to() == self.seeder,
        )

    @external
    def claim(self):
        claimer_optin, snd_asset, close_to_seeder = Gtxn[0], Gtxn[1], Gtxn[2]
        return And(
            Global.group_size() == Int(3),
            # Make sure the signature matches
            If(
                Txn.group_index() == Int(1),
                Ed25519Verify(Txn.tx_id(), Arg(1), Tmpl.Bytes("TMPL_GEN_ADDR")),
                Int(1),
            ),
            # Account Opt in
            claimer_optin.type_enum() == TxnType.AssetTransfer,
            claimer_optin.sender() == Gtxn[0].asset_receiver(),
            claimer_optin.asset_amount() == Int(0),
            claimer_optin.asset_close_to() == Global.zero_address(),
            # Close Asset to Account
            snd_asset.type_enum() == TxnType.AssetTransfer,
            snd_asset.asset_amount() == Int(0),
            snd_asset.xfer_asset() == Gtxn[0].xfer_asset(),
            snd_asset.asset_close_to() == Gtxn[0].sender(),
            # Close algos back to seeder
            close_to_seeder.type_enum() == TxnType.Payment,
            close_to_seeder.amount() == Int(0),
            close_to_seeder.close_remainder_to() == self.seeder,
        )


if __name__ == "__main__":
    from beaker.sandbox import get_accounts

    accts = get_accounts()
    addr, sk = accts.pop()
    mls = MyLsig(addr)
    print(mls)
