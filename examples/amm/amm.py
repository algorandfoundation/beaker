from typing import Final
from pyteal import (
    abi,
    pragma,
    TealType,
    Bytes,
    Global,
    Expr,
    Int,
    Seq,
    Assert,
    Txn,
    And,
    ScratchVar,
    AssetHolding,
    AssetParam,
    WideRatio,
    If,
    Or,
    InnerTxn,
    InnerTxnBuilder,
    TxnField,
    Concat,
    TxnType,
    Sqrt,
)

from beaker import (
    consts,
    ApplicationStateValue,
    Application,
    Authorize,
    external,
    create,
    internal,
)

# WARNING: This code is provided for example only. Do NOT deploy to mainnet.

pragma(compiler_version="^0.19.0")


def commented_assert(conditions: list[tuple[Expr, str]]) -> list[Expr]:
    return [Assert(cond, comment=cmt) for cond, cmt in conditions]


class ConstantProductAMMErrors:
    GroupSizeNot2 = "group size not 2"
    ReceiverNotAppAddr = "receiver not app address"
    AmountLessThanMinimum = "amount minimum not met"
    AssetIdsIncorrect = "asset a or asset b incorrect"
    AssetAIncorrect = "asset a incorrect"
    AssetBIncorrect = "asset b incorrect"
    AssetPoolIncorrect = "asset pool incorrect"
    SenderInvalid = "invalid sender"
    MissingBalances = "missing required balances"
    SendAmountTooLow = "outgoing amount too low"


class ConstantProductAMM(Application):

    # Declare Application state, marking `Final` here so the python class var doesn't get changed
    # Marking a var `Final` does _not_ change anything at the AVM level
    governor: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        key=Bytes("g"),
        default=Global.creator_address(),
        descr="The current governor of this contract, allowed to do admin type actions",
    )
    asset_a: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("a"),
        static=True,
        descr="The asset id of asset A",
    )
    asset_b: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("b"),
        static=True,
        descr="The asset id of asset B",
    )
    pool_token: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("p"),
        static=True,
        descr="The asset id of the Pool Token, used to track share of pool the holder may recover",
    )
    ratio: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("r"),
        descr="The ratio between assets (A/B)*Scale",
    )

    ##############
    # Constants
    ##############

    # Total supply of the pool tokens
    _total_supply: Final[int] = int(1e10)
    total_supply: Final[Expr] = Int(_total_supply)
    # scale helps with precision when doing computation for
    # the number of tokens to transfer
    _scale: Final[int] = 1000
    scale: Final[Expr] = Int(_scale)
    # Fee for swaps, 5 represents 0.5% ((fee / scale)*100)
    _fee: Final[int] = 5
    fee: Final[Expr] = Int(_fee)

    ##############
    # Administrative Actions
    ##############

    # Call this only on create
    @create
    def create(self):
        return self.initialize_application_state()

    # Only the account set in app_state.governor may call this method
    @external(authorize=Authorize.only(governor))
    def set_governor(self, new_governor: abi.Account):
        """sets the governor of the contract, may only be called by the current governor"""
        return self.governor.set(new_governor.address())

    # Only the account set in app_state.governor may call this method
    @external(authorize=Authorize.only(governor))
    def bootstrap(
        self,
        seed: abi.PaymentTransaction,
        a_asset: abi.Asset,
        b_asset: abi.Asset,
        *,
        output: abi.Uint64,
    ):
        """bootstraps the contract by opting into the assets and creating the pool token.

        Note this method will fail if it is attempted more than once on the same contract since the assets and pool token
        application state values are marked as static and cannot be overridden.

        Args:
            seed: Initial Payment transaction to the app account so it can opt in to assets and create pool token.
            a_asset: One of the two assets this pool should allow swapping between.
            b_asset: The other of the two assets this pool should allow swapping between.

        Returns:
            The asset id of the pool token created.
        """

        well_formed_bootstrap = [
            (Global.group_size() == Int(2), ConstantProductAMMErrors.GroupSizeNot2),
            (
                seed.get().receiver() == self.address,
                ConstantProductAMMErrors.ReceiverNotAppAddr,
            ),
            (
                seed.get().amount() >= consts.Algos(0.3),
                ConstantProductAMMErrors.AmountLessThanMinimum,
            ),
            (
                a_asset.asset_id() < b_asset.asset_id(),
                ConstantProductAMMErrors.AssetIdsIncorrect,
            ),
        ]

        return Seq(
            *commented_assert(well_formed_bootstrap),
            self.asset_a.set(a_asset.asset_id()),
            self.asset_b.set(b_asset.asset_id()),
            self.pool_token.set(
                self.do_create_pool_token(
                    self.asset_a,
                    self.asset_b,
                ),
            ),
            self.do_opt_in(self.asset_a),
            self.do_opt_in(self.asset_b),
            output.set(self.pool_token),
        )

    ##############
    # AMM specific methods for mint/burn/swap
    ##############

    @external
    def mint(
        self,
        a_xfer: abi.AssetTransferTransaction,
        b_xfer: abi.AssetTransferTransaction,
        pool_asset: abi.Asset = pool_token,  # type: ignore[assignment]
        a_asset: abi.Asset = asset_a,  # type: ignore[assignment]
        b_asset: abi.Asset = asset_b,  # type: ignore[assignment]
    ):
        """mint pool tokens given some amount of asset A and asset B.

        Given some amount of Asset A and Asset B in the transfers, mint some number of pool tokens commensurate with
        the pools current balance and circulating supply of pool tokens.

        Args:
            a_xfer: Asset Transfer Transaction of asset A as a deposit to the pool in exchange for pool tokens.
            b_xfer: Asset Transfer Transaction of asset B as a deposit to the pool in exchange for pool tokens.
            pool_asset: The asset ID of the pool token so that we may distribute it.
            a_asset: The asset ID of the Asset A so that we may inspect our balance.
            b_asset: The asset ID of the Asset B so that we may inspect our balance.
        """

        well_formed_mint = [
            (
                a_asset.asset_id() == self.asset_a,
                ConstantProductAMMErrors.AssetAIncorrect,
            ),
            (
                b_asset.asset_id() == self.asset_b,
                ConstantProductAMMErrors.AssetBIncorrect,
            ),
            (
                pool_asset.asset_id() == self.pool_token,
                ConstantProductAMMErrors.AssetPoolIncorrect,
            ),
        ]

        valid_asset_a_xfer = [
            (
                a_xfer.get().asset_receiver() == self.address,
                ConstantProductAMMErrors.ReceiverNotAppAddr,
            ),
            (
                a_xfer.get().xfer_asset() == self.asset_a,
                ConstantProductAMMErrors.AssetAIncorrect,
            ),
            (
                a_xfer.get().asset_amount() > Int(0),
                ConstantProductAMMErrors.AmountLessThanMinimum,
            ),
            (
                a_xfer.get().sender() == Txn.sender(),
                ConstantProductAMMErrors.SenderInvalid,
            ),
        ]

        valid_asset_b_xfer = [
            (
                b_xfer.get().asset_receiver() == self.address,
                ConstantProductAMMErrors.ReceiverNotAppAddr,
            ),
            (
                b_xfer.get().xfer_asset() == self.asset_b,
                ConstantProductAMMErrors.AssetBIncorrect,
            ),
            (
                b_xfer.get().asset_amount() > Int(0),
                ConstantProductAMMErrors.AmountLessThanMinimum,
            ),
            (
                b_xfer.get().sender() == Txn.sender(),
                ConstantProductAMMErrors.SenderInvalid,
            ),
        ]

        return Seq(
            # Check that the transaction is constructed correctly
            *commented_assert(
                well_formed_mint + valid_asset_a_xfer + valid_asset_b_xfer
            ),
            # Check that we have these things
            pool_bal := pool_asset.holding(self.address).balance(),
            a_bal := a_asset.holding(self.address).balance(),
            b_bal := b_asset.holding(self.address).balance(),
            Assert(
                pool_bal.hasValue(),
                a_bal.hasValue(),
                b_bal.hasValue(),
                comment=ConstantProductAMMErrors.MissingBalances,
            ),
            (to_mint := ScratchVar()).store(
                If(
                    And(
                        a_bal.value() == a_xfer.get().asset_amount(),
                        b_bal.value() == b_xfer.get().asset_amount(),
                    ),
                    # This is the first time we've been called
                    # we use a different formula to mint tokens
                    self.tokens_to_mint_initial(
                        a_xfer.get().asset_amount(), b_xfer.get().asset_amount()
                    ),
                    # Normal mint
                    self.tokens_to_mint(
                        self.total_supply - pool_bal.value(),
                        a_bal.value() - a_xfer.get().asset_amount(),
                        b_bal.value() - b_xfer.get().asset_amount(),
                        a_xfer.get().asset_amount(),
                        b_xfer.get().asset_amount(),
                    ),
                )
            ),
            Assert(
                to_mint.load() > Int(0),
                comment=ConstantProductAMMErrors.SendAmountTooLow,
            ),
            # mint tokens
            self.do_axfer(Txn.sender(), self.pool_token, to_mint.load()),
            self.ratio.set(self.compute_ratio()),
        )

    @external
    def burn(
        self,
        pool_xfer: abi.AssetTransferTransaction,
        pool_asset: abi.Asset = pool_token,  # type: ignore[assignment]
        a_asset: abi.Asset = asset_a,  # type: ignore[assignment]
        b_asset: abi.Asset = asset_b,  # type: ignore[assignment]
    ):
        """burn pool tokens to get back some amount of asset A and asset B

        Args:
            pool_xfer: Asset Transfer Transaction of the pool token for the amount the sender wishes to redeem
            pool_asset: Asset ID of the pool token so we may inspect balance.
            a_asset: Asset ID of Asset A so we may inspect balance and distribute it
            b_asset: Asset ID of Asset B so we may inspect balance and distribute it
        """

        well_formed_burn = [
            (
                pool_asset.asset_id() == self.pool_token,
                ConstantProductAMMErrors.AssetPoolIncorrect,
            ),
            (
                a_asset.asset_id() == self.asset_a,
                ConstantProductAMMErrors.AssetAIncorrect,
            ),
            (
                b_asset.asset_id() == self.asset_b,
                ConstantProductAMMErrors.AssetBIncorrect,
            ),
        ]

        valid_pool_xfer = [
            (
                pool_xfer.get().asset_receiver() == self.address,
                ConstantProductAMMErrors.ReceiverNotAppAddr,
            ),
            (
                pool_xfer.get().asset_amount() > Int(0),
                ConstantProductAMMErrors.AmountLessThanMinimum,
            ),
            (
                pool_xfer.get().xfer_asset() == self.pool_token,
                ConstantProductAMMErrors.AssetPoolIncorrect,
            ),
            (
                pool_xfer.get().sender() == Txn.sender(),
                ConstantProductAMMErrors.SenderInvalid,
            ),
        ]

        return Seq(
            *commented_assert(well_formed_burn + valid_pool_xfer),
            pool_bal := pool_asset.holding(self.address).balance(),
            a_bal := a_asset.holding(self.address).balance(),
            b_bal := b_asset.holding(self.address).balance(),
            Assert(
                pool_bal.hasValue(),
                a_bal.hasValue(),
                b_bal.hasValue(),
                comment=ConstantProductAMMErrors.MissingBalances,
            ),
            # Get the total number of tokens issued (prior to receiving the current axfer of pool tokens)
            (issued := ScratchVar()).store(
                self.total_supply - (pool_bal.value() - pool_xfer.get().asset_amount())
            ),
            (a_amt := ScratchVar()).store(
                self.tokens_to_burn(
                    issued.load(),
                    a_bal.value(),
                    pool_xfer.get().asset_amount(),
                )
            ),
            (b_amt := ScratchVar()).store(
                self.tokens_to_burn(
                    issued.load(),
                    b_bal.value(),
                    pool_xfer.get().asset_amount(),
                )
            ),
            # Send back commensurate amt of a
            self.do_axfer(
                Txn.sender(),
                self.asset_a,
                a_amt.load(),
            ),
            # Send back commensurate amt of b
            self.do_axfer(
                Txn.sender(),
                self.asset_b,
                b_amt.load(),
            ),
            self.ratio.set(self.compute_ratio()),
        )

    @external
    def swap(
        self,
        swap_xfer: abi.AssetTransferTransaction,
        a_asset: abi.Asset = asset_a,  # type: ignore[assignment]
        b_asset: abi.Asset = asset_b,  # type: ignore[assignment]
    ):
        """Swap some amount of either asset A or asset B for the other

        Args:
            swap_xfer: Asset Transfer Transaction of either Asset A or Asset B
            a_asset: Asset ID of asset A so we may inspect balance and possibly transfer it
            b_asset: Asset ID of asset B so we may inspect balance and possibly transfer it
        """
        well_formed_swap = [
            (
                a_asset.asset_id() == self.asset_a,
                ConstantProductAMMErrors.AssetAIncorrect,
            ),
            (
                b_asset.asset_id() == self.asset_b,
                ConstantProductAMMErrors.AssetBIncorrect,
            ),
        ]

        valid_swap_xfer = [
            (
                Or(
                    swap_xfer.get().xfer_asset() == self.asset_a,
                    swap_xfer.get().xfer_asset() == self.asset_b,
                ),
                ConstantProductAMMErrors.AssetIdsIncorrect,
            ),
            (
                swap_xfer.get().asset_amount() > Int(0),
                ConstantProductAMMErrors.AmountLessThanMinimum,
            ),
            (
                swap_xfer.get().sender() == Txn.sender(),
                ConstantProductAMMErrors.SenderInvalid,
            ),
        ]

        out_id = If(
            swap_xfer.get().xfer_asset() == self.asset_a,
            self.asset_b,
            self.asset_a,
        )
        in_id = swap_xfer.get().xfer_asset()

        return Seq(
            *commented_assert(well_formed_swap + valid_swap_xfer),
            in_sup := AssetHolding.balance(self.address, in_id),
            out_sup := AssetHolding.balance(self.address, out_id),
            Assert(
                in_sup.hasValue(),
                out_sup.hasValue(),
                comment=ConstantProductAMMErrors.MissingBalances,
            ),
            (to_swap := ScratchVar()).store(
                self.tokens_to_swap(
                    swap_xfer.get().asset_amount(),
                    in_sup.value() - swap_xfer.get().asset_amount(),
                    out_sup.value(),
                )
            ),
            Assert(
                to_swap.load() > Int(0),
                comment=ConstantProductAMMErrors.SendAmountTooLow,
            ),
            self.do_axfer(
                Txn.sender(),
                out_id,
                to_swap.load(),
            ),
            self.ratio.set(self.compute_ratio()),
        )

    ##############
    # Mathy methods
    ##############

    # Notes:
    #   1) During arithmetic operations, depending on the inputs, these methods may overflow
    #   the max uint64 value. This will cause the program to immediately terminate.
    #
    #   Care should be taken to fully understand the limitations of these functions and if
    #   required should be swapped out for the appropriate byte math operations.
    #
    #   2) When doing division, any remainder is truncated from the result.
    #
    #   Care should be taken  to ensure that _when_ the truncation happens,
    #   it does so in favor of the contract. This is a subtle security issue that,
    #   if mishandled, could cause the balance of the contract to be drained.

    @internal(TealType.uint64)
    def tokens_to_mint(self, issued, a_supply, b_supply, a_amount, b_amount):
        return Seq(
            (a_rat := ScratchVar()).store(
                WideRatio([a_amount, self.scale], [a_supply])
            ),
            (b_rat := ScratchVar()).store(
                WideRatio([b_amount, self.scale], [b_supply])
            ),
            WideRatio(
                [If(a_rat.load() < b_rat.load(), a_rat.load(), b_rat.load()), issued],
                [self.scale],
            ),
        )

    @internal(TealType.uint64)
    def tokens_to_mint_initial(self, a_amount, b_amount):
        return Sqrt(a_amount * b_amount) - self.scale

    @internal(TealType.uint64)
    def tokens_to_burn(self, issued, supply, amount):
        return WideRatio([supply, amount], [issued])

    @internal(TealType.uint64)
    def tokens_to_swap(self, in_amount, in_supply, out_supply):
        factor = self.scale - self.fee
        return WideRatio(
            [in_amount, factor, out_supply],
            [(in_supply * self.scale) + (in_amount * factor)],
        )

    ##############
    # Utility methods for inner transactions
    ##############

    @internal(TealType.none)
    def do_axfer(self, rx, aid, amt):
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: aid,
                TxnField.asset_amount: amt,
                TxnField.asset_receiver: rx,
                TxnField.fee: Int(0),
            }
        )

    @internal(TealType.none)
    def do_opt_in(self, aid):
        return self.do_axfer(self.address, aid, Int(0))

    @internal(TealType.uint64)
    def do_create_pool_token(self, a, b):
        return Seq(
            una := AssetParam.unitName(a),
            unb := AssetParam.unitName(b),
            Assert(
                una.hasValue(),
                unb.hasValue(),
                comment=ConstantProductAMMErrors.MissingBalances,
            ),
            InnerTxnBuilder.Execute(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: Concat(
                        Bytes("DPT-"), una.value(), Bytes("-"), unb.value()
                    ),
                    TxnField.config_asset_unit_name: Bytes("dpt"),
                    TxnField.config_asset_total: self.total_supply,
                    TxnField.config_asset_decimals: Int(3),
                    TxnField.config_asset_manager: self.address,
                    TxnField.config_asset_reserve: self.address,
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxn.created_asset_id(),
        )

    @internal(TealType.uint64)
    def compute_ratio(self):
        return Seq(
            bal_a := AssetHolding.balance(
                self.address,
                self.asset_a,
            ),
            bal_b := AssetHolding.balance(
                self.address,
                self.asset_b,
            ),
            Assert(
                bal_a.hasValue(),
                bal_b.hasValue(),
                comment=ConstantProductAMMErrors.MissingBalances,
            ),
            WideRatio([bal_a.value(), self.scale], [bal_b.value()]),
        )


if __name__ == "__main__":
    ConstantProductAMM().dump("artifacts")
