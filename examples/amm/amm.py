from typing import Final
from pyteal import *

from beaker import (
    GlobalStateValue,
    ApplicationState,
    Application,
    Authorize,
    handler,
    internal,
)
from beaker.decorators import bare_handler

# WARNING: THIS IS NOT PROODUCTION LEVEL CODE
# Seriously, there are _definitely_ bugs in the math


class ConstantProductAMM(Application):

    governor = GlobalStateValue(
        stack_type=TealType.bytes,
        key=Bytes("g"),
        default=Global.creator_address(),
        descr="The current governor of this contract, allowed to do admin type actions",
    )
    asset_a = GlobalStateValue(
        stack_type=TealType.uint64,
        key=Bytes("a"),
        static=True,
        descr="The asset id of asset A",
    )
    asset_b = GlobalStateValue(
        stack_type=TealType.uint64,
        key=Bytes("b"),
        static=True,
        descr="The asset id of asset B",
    )
    pool_token = GlobalStateValue(
        stack_type=TealType.uint64,
        key=Bytes("p"),
        static=True,
        descr="The asset id of the Pool Token, used to track share of pool the holder may recover",
    )
    ratio = GlobalStateValue(
        stack_type=TealType.uint64,
        key=Bytes("r"),
        descr="The ratio between assets (A/B)*Scale",
    )

    ##############
    # Constants
    ##############

    # Total supply of the pool tokens
    total_supply: Final[Expr] = Int(int(1e10))
    # scale helps with precision when doing computation for
    # the number of tokens to transfer
    scale: Final[Expr] = Int(1000)
    # Fee for swaps, 5 represents 0.5% ((fee / scale)*100)
    fee: Final[Expr] = Int(5)

    ##############
    # Administrative Actions
    ##############

    # Call this only on create
    @bare_handler(no_op=CallConfig.CREATE)
    def create(self):
        return self.initialize_app_state()

    # Only the account set in app_state.governor may call this method
    @handler(authorize=Authorize.only(governor))
    def set_governor(new_governor: abi.Account):
        """sets the governor of the contract, may only be called by the current governor"""
        return ConstantProductAMM.governor.set(new_governor.address())

    # Only the account set in app_state.governor may call this method
    @handler(authorize=Authorize.only(governor))
    def bootstrap(a_asset: abi.Asset, b_asset: abi.Asset, *, output: abi.Uint64):
        """bootstraps the contract by opting into the assets and creating the pool token"""
        well_formed_bootstrap = And(
            Global.group_size() == Int(1),
            a_asset.asset_id() < b_asset.asset_id(),
        )

        return Seq(
            Assert(well_formed_bootstrap),
            ConstantProductAMM.asset_a.set(a_asset.asset_id()),
            ConstantProductAMM.asset_b.set(b_asset.asset_id()),
            ConstantProductAMM.pool_token.set(
                ConstantProductAMM.do_create_pool_token(
                    ConstantProductAMM.asset_a,
                    ConstantProductAMM.asset_b,
                ),
            ),
            ConstantProductAMM.do_opt_in(ConstantProductAMM.asset_a),
            ConstantProductAMM.do_opt_in(ConstantProductAMM.asset_b),
            output.set(ConstantProductAMM.pool_token),
        )

    ##############
    # AMM specific methods for mint/burn/swap
    ##############

    @handler
    def mint(
        a_xfer: abi.AssetTransferTransaction,
        b_xfer: abi.AssetTransferTransaction,
        pool_asset: abi.Asset,
        a_asset: abi.Asset,
        b_asset: abi.Asset,
    ):
        """mint pool tokens given some amount of asset A and asset B"""

        well_formed_mint = And(
            a_asset.asset_id() == ConstantProductAMM.asset_a,
            b_asset.asset_id() == ConstantProductAMM.asset_b,
            pool_asset.asset_id() == ConstantProductAMM.pool_token,
        )

        valid_asset_a_xfer = And(
            a_xfer.get().asset_receiver() == ConstantProductAMM.address,
            a_xfer.get().xfer_asset() == ConstantProductAMM.asset_a,
            a_xfer.get().asset_amount() > Int(0),
            a_xfer.get().sender() == Txn.sender(),
        )

        valid_asset_b_xfer = And(
            b_xfer.get().asset_receiver() == ConstantProductAMM.address,
            b_xfer.get().xfer_asset() == ConstantProductAMM.asset_b,
            b_xfer.get().asset_amount() > Int(0),
            b_xfer.get().sender() == Txn.sender(),
        )

        return Seq(
            # Check that the transaction is constructed correctly
            Assert(well_formed_mint),
            Assert(valid_asset_a_xfer),
            Assert(valid_asset_b_xfer),
            # Check that we have these things
            pool_bal := pool_asset.holding(ConstantProductAMM.address).balance(),
            a_bal := a_asset.holding(ConstantProductAMM.address).balance(),
            b_bal := b_asset.holding(ConstantProductAMM.address).balance(),
            Assert(And(pool_bal.hasValue(), a_bal.hasValue(), b_bal.hasValue())),
            # mint tokens
            ConstantProductAMM.do_axfer(
                Txn.sender(),
                ConstantProductAMM.pool_token,
                If(
                    And(
                        a_bal.value() == a_xfer.get().asset_amount(),
                        b_bal.value() == b_xfer.get().asset_amount(),
                    ),
                    # This is the first time we've been called
                    # we use a different formula to mint tokens
                    ConstantProductAMM.tokens_to_mint_initial(
                        a_xfer.get().asset_amount(), b_xfer.get().asset_amount()
                    ),
                    # Normal mint
                    ConstantProductAMM.tokens_to_mint(
                        ConstantProductAMM.total_supply - pool_bal.value(),
                        a_bal.value(),
                        b_bal.value(),
                        a_xfer.get().asset_amount(),
                        b_xfer.get().asset_amount(),
                    ),
                ),
            ),
            ConstantProductAMM.ratio.set(ConstantProductAMM.get_ratio()),
        )

    @handler
    def burn(
        pool_xfer: abi.AssetTransferTransaction,
        pool_asset: abi.Asset,
        a_asset: abi.Asset,
        b_asset: abi.Asset,
    ):
        """burn pool tokens to get back some amount of asset A and asset B"""

        well_formed_burn = And(
            pool_asset.asset_id() == ConstantProductAMM.pool_token,
            a_asset.asset_id() == ConstantProductAMM.asset_a,
            b_asset.asset_id() == ConstantProductAMM.asset_b,
        )

        valid_pool_xfer = And(
            pool_xfer.get().asset_receiver() == ConstantProductAMM.address,
            pool_xfer.get().asset_amount() > Int(0),
            pool_xfer.get().xfer_asset() == ConstantProductAMM.pool_token,
            pool_xfer.get().sender() == Txn.sender(),
        )

        return Seq(
            Assert(well_formed_burn),
            Assert(valid_pool_xfer),
            pool_bal := pool_asset.holding(ConstantProductAMM.address).balance(),
            a_bal := a_asset.holding(ConstantProductAMM.address).balance(),
            b_bal := b_asset.holding(ConstantProductAMM.address).balance(),
            Assert(And(pool_bal.hasValue(), a_bal.hasValue(), b_bal.hasValue())),
            # Get the total number of tokens issued (prior to receiving the current axfer of pool tokens)
            (issued := ScratchVar()).store(
                ConstantProductAMM.total_supply
                - (pool_bal.value() - pool_xfer.get().asset_amount())
            ),
            # Send back commensurate amt of a
            ConstantProductAMM.do_axfer(
                Txn.sender(),
                ConstantProductAMM.asset_a,
                ConstantProductAMM.tokens_to_burn(
                    issued.load(),
                    a_bal.value(),
                    pool_xfer.get().asset_amount(),
                ),
            ),
            # Send back commensurate amt of b
            ConstantProductAMM.do_axfer(
                Txn.sender(),
                ConstantProductAMM.asset_b,
                ConstantProductAMM.tokens_to_burn(
                    issued.load(),
                    b_bal.value(),
                    pool_xfer.get().asset_amount(),
                ),
            ),
            # The ratio should be the same before and after
            Assert(ConstantProductAMM.ratio == ConstantProductAMM.get_ratio()),
        )

    @handler
    def swap(
        swap_xfer: abi.AssetTransferTransaction,
        a_asset: abi.Asset,
        b_asset: abi.Asset,
    ):
        """Swap some amount of either asset A or asset B for the other"""
        well_formed_swap = And(
            a_asset.asset_id() == ConstantProductAMM.asset_a,
            b_asset.asset_id() == ConstantProductAMM.asset_b,
        )

        valid_swap_xfer = And(
            Or(
                swap_xfer.get().xfer_asset() == ConstantProductAMM.asset_a,
                swap_xfer.get().xfer_asset() == ConstantProductAMM.asset_b,
            ),
            swap_xfer.get().asset_amount() > Int(0),
            swap_xfer.get().sender() == Txn.sender(),
        )

        out_id = If(
            swap_xfer.get().xfer_asset() == ConstantProductAMM.asset_a,
            ConstantProductAMM.asset_b,
            ConstantProductAMM.asset_a,
        )
        in_id = swap_xfer.get().xfer_asset()

        return Seq(
            Assert(well_formed_swap),
            Assert(valid_swap_xfer),
            in_sup := AssetHolding.balance(ConstantProductAMM.address, in_id),
            out_sup := AssetHolding.balance(ConstantProductAMM.address, out_id),
            Assert(And(in_sup.hasValue(), out_sup.hasValue())),
            ConstantProductAMM.do_axfer(
                Txn.sender(),
                out_id,
                ConstantProductAMM.tokens_to_swap(
                    swap_xfer.get().asset_amount(), in_sup.value(), out_sup.value()
                ),
            ),
            ConstantProductAMM.ratio.set(ConstantProductAMM.get_ratio()),
        )

    ##############
    # Mathy methods
    ##############

    @internal(TealType.uint64)
    def tokens_to_mint(issued, a_supply, b_supply, a_amount, b_amount):
        return Seq(
            (a_rat := ScratchVar()).store(
                WideRatio([a_amount, ConstantProductAMM.scale], [a_supply])
            ),
            (b_rat := ScratchVar()).store(
                WideRatio([b_amount, ConstantProductAMM.scale], [b_supply])
            ),
            WideRatio(
                [If(a_rat.load() < b_rat.load(), a_rat.load(), b_rat.load()), issued],
                [ConstantProductAMM.scale],
            ),
        )

    @internal(TealType.uint64)
    def tokens_to_mint_initial(a_amount, b_amount):
        return Sqrt(a_amount * b_amount) - ConstantProductAMM.scale

    @internal(TealType.uint64)
    def tokens_to_burn(issued, supply, amount):
        return WideRatio([supply, amount], [issued])

    @internal(TealType.uint64)
    def tokens_to_swap(in_amount, in_supply, out_supply):
        factor = ConstantProductAMM.scale - ConstantProductAMM.fee
        return WideRatio(
            [in_amount, factor, out_supply],
            [(in_supply * ConstantProductAMM.scale) + (in_amount * factor)],
        )

    ##############
    # Utility methods for inner transactions
    ##############

    @internal(TealType.none)
    def do_axfer(rx, aid, amt):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: aid,
                    TxnField.asset_amount: amt,
                    TxnField.asset_receiver: rx,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    @internal(TealType.none)
    def do_opt_in(aid):
        return ConstantProductAMM.do_axfer(ConstantProductAMM.address, aid, Int(0))

    @internal(TealType.uint64)
    def do_create_pool_token(a, b):
        return Seq(
            una := AssetParam.unitName(a),
            unb := AssetParam.unitName(b),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: Concat(
                        Bytes("DPT-"), una.value(), Bytes("-"), unb.value()
                    ),
                    TxnField.config_asset_unit_name: Bytes("dpt"),
                    TxnField.config_asset_total: ConstantProductAMM.total_supply,
                    TxnField.config_asset_decimals: Int(3),
                    TxnField.config_asset_manager: ConstantProductAMM.address,
                    TxnField.config_asset_reserve: ConstantProductAMM.address,
                }
            ),
            InnerTxnBuilder.Submit(),
            InnerTxn.created_asset_id(),
        )

    @internal(TealType.uint64)
    def get_ratio():
        return Seq(
            bal_a := AssetHolding.balance(
                ConstantProductAMM.address,
                ConstantProductAMM.asset_a,
            ),
            bal_b := AssetHolding.balance(
                ConstantProductAMM.address,
                ConstantProductAMM.asset_b,
            ),
            Assert(And(bal_a.hasValue(), bal_b.hasValue())),
            WideRatio([bal_a.value(), ConstantProductAMM.scale], [bal_b.value()]),
        )


if __name__ == "__main__":
    import json

    amm = ConstantProductAMM()
    print(f"\nApproval program:\n{amm.approval_program}")
    # print(f"\nClear State program:\n{amm.approval_program}")
    # print(f"\nabi:\n{json.dumps(amm.contract.dictify(), indent=2)}")
