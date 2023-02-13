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
    Subroutine,
)

from beaker import (
    consts,
    ApplicationStateValue,
    Application,
    Authorize,
    unconditional_create_approval,
)

# WARNING: This code is provided for example only. Do NOT deploy to mainnet.

pragma(compiler_version="^0.22.0")


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


class ConstantProductAMMState:
    asset_a = ApplicationStateValue(
        stack_type=TealType.uint64,
        key="a",
        static=True,
        descr="The asset id of asset A",
    )
    asset_b = ApplicationStateValue(
        stack_type=TealType.uint64,
        key="b",
        static=True,
        descr="The asset id of asset B",
    )
    governor = ApplicationStateValue(
        stack_type=TealType.bytes,
        key="g",
        default=Global.creator_address(),
        descr="The current governor of this contract, allowed to do admin type actions",
    )
    pool_token = ApplicationStateValue(
        stack_type=TealType.uint64,
        key="p",
        static=True,
        descr="The asset id of the Pool Token, used to track share of pool the holder may recover",
    )
    ratio = ApplicationStateValue(
        stack_type=TealType.uint64,
        key="r",
        descr="The ratio between assets (A/B)*Scale",
    )


amm_app = Application("ConstantProductAMM", state=ConstantProductAMMState()).implement(
    unconditional_create_approval, initialize_app_state=True
)
##############
# Constants
##############

# Total supply of the pool tokens
total_supply: Final[int] = int(1e10)
total_supply_expr: Final[Int] = Int(total_supply)
# scale helps with precision when doing computation for
# the number of tokens to transfer
scale: Final[int] = 1000
scale_expr: Final[Int] = Int(scale)
# Fee for swaps, 5 represents 0.5% ((fee / scale)*100)
fee: Final[int] = 5
fee_expr: Final[Int] = Int(fee)


# Only the account set in app_state.governor may call this method
@amm_app.external(authorize=Authorize.only(amm_app.state.governor))
def set_governor(new_governor: abi.Account) -> Expr:
    """sets the governor of the contract, may only be called by the current governor"""
    return amm_app.state.governor.set(new_governor.address())


# Only the account set in app_state.governor may call this method
@amm_app.external(authorize=Authorize.only(amm_app.state.governor))
def bootstrap(
    seed: abi.PaymentTransaction,
    a_asset: abi.Asset,
    b_asset: abi.Asset,
    *,
    output: abi.Uint64,
) -> Expr:
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
            seed.get().receiver() == Global.current_application_address(),
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
        amm_app.state.asset_a.set(a_asset.asset_id()),
        amm_app.state.asset_b.set(b_asset.asset_id()),
        amm_app.state.pool_token.set(
            do_create_pool_token(
                amm_app.state.asset_a,
                amm_app.state.asset_b,
            ),
        ),
        do_opt_in(amm_app.state.asset_a),
        do_opt_in(amm_app.state.asset_b),
        output.set(amm_app.state.pool_token),
    )


##############
# AMM specific methods for mint/burn/swap
##############


@amm_app.external
def mint(
    a_xfer: abi.AssetTransferTransaction,
    b_xfer: abi.AssetTransferTransaction,
    pool_asset: abi.Asset = amm_app.state.pool_token,  # type: ignore[assignment]
    a_asset: abi.Asset = amm_app.state.asset_a,  # type: ignore[assignment]
    b_asset: abi.Asset = amm_app.state.asset_b,  # type: ignore[assignment]
) -> Expr:
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
            a_asset.asset_id() == amm_app.state.asset_a,
            ConstantProductAMMErrors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == amm_app.state.asset_b,
            ConstantProductAMMErrors.AssetBIncorrect,
        ),
        (
            pool_asset.asset_id() == amm_app.state.pool_token,
            ConstantProductAMMErrors.AssetPoolIncorrect,
        ),
        (
            And(
                a_xfer.get().sender() == Txn.sender(),
                b_xfer.get().sender() == Txn.sender(),
            ),
            ConstantProductAMMErrors.SenderInvalid,
        ),
    ]

    valid_asset_a_xfer = [
        (
            a_xfer.get().asset_receiver() == Global.current_application_address(),
            ConstantProductAMMErrors.ReceiverNotAppAddr,
        ),
        (
            a_xfer.get().xfer_asset() == amm_app.state.asset_a,
            ConstantProductAMMErrors.AssetAIncorrect,
        ),
        (
            a_xfer.get().asset_amount() > Int(0),
            ConstantProductAMMErrors.AmountLessThanMinimum,
        ),
    ]

    valid_asset_b_xfer = [
        (
            b_xfer.get().asset_receiver() == Global.current_application_address(),
            ConstantProductAMMErrors.ReceiverNotAppAddr,
        ),
        (
            b_xfer.get().xfer_asset() == amm_app.state.asset_b,
            ConstantProductAMMErrors.AssetBIncorrect,
        ),
        (
            b_xfer.get().asset_amount() > Int(0),
            ConstantProductAMMErrors.AmountLessThanMinimum,
        ),
    ]

    return Seq(
        # Check that the transaction is constructed correctly
        *commented_assert(well_formed_mint + valid_asset_a_xfer + valid_asset_b_xfer),
        # Check that we have these things
        pool_bal := pool_asset.holding(Global.current_application_address()).balance(),
        a_bal := a_asset.holding(Global.current_application_address()).balance(),
        b_bal := b_asset.holding(Global.current_application_address()).balance(),
        Assert(
            pool_bal.hasValue(),
            a_bal.hasValue(),
            b_bal.hasValue(),
        ),
        (to_mint := ScratchVar()).store(
            If(
                And(
                    a_bal.value() == a_xfer.get().asset_amount(),
                    b_bal.value() == b_xfer.get().asset_amount(),
                ),
                # This is the first time we've been called
                # we use a different formula to mint tokens
                tokens_to_mint_initial(
                    a_xfer.get().asset_amount(), b_xfer.get().asset_amount()
                ),
                # Normal mint
                tokens_to_mint(
                    total_supply_expr - pool_bal.value(),
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
        do_axfer(Txn.sender(), amm_app.state.pool_token, to_mint.load()),
        amm_app.state.ratio.set(compute_ratio()),
    )


@amm_app.external
def burn(
    pool_xfer: abi.AssetTransferTransaction,
    pool_asset: abi.Asset = amm_app.state.pool_token,  # type: ignore[assignment]
    a_asset: abi.Asset = amm_app.state.asset_a,  # type: ignore[assignment]
    b_asset: abi.Asset = amm_app.state.asset_b,  # type: ignore[assignment]
) -> Expr:
    """burn pool tokens to get back some amount of asset A and asset B

    Args:
        pool_xfer: Asset Transfer Transaction of the pool token for the amount the sender wishes to redeem
        pool_asset: Asset ID of the pool token so we may inspect balance.
        a_asset: Asset ID of Asset A so we may inspect balance and distribute it
        b_asset: Asset ID of Asset B so we may inspect balance and distribute it
    """

    well_formed_burn = [
        (
            pool_asset.asset_id() == amm_app.state.pool_token,
            ConstantProductAMMErrors.AssetPoolIncorrect,
        ),
        (
            a_asset.asset_id() == amm_app.state.asset_a,
            ConstantProductAMMErrors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == amm_app.state.asset_b,
            ConstantProductAMMErrors.AssetBIncorrect,
        ),
    ]

    valid_pool_xfer = [
        (
            pool_xfer.get().asset_receiver() == Global.current_application_address(),
            ConstantProductAMMErrors.ReceiverNotAppAddr,
        ),
        (
            pool_xfer.get().asset_amount() > Int(0),
            ConstantProductAMMErrors.AmountLessThanMinimum,
        ),
        (
            pool_xfer.get().xfer_asset() == amm_app.state.pool_token,
            ConstantProductAMMErrors.AssetPoolIncorrect,
        ),
        (
            pool_xfer.get().sender() == Txn.sender(),
            ConstantProductAMMErrors.SenderInvalid,
        ),
    ]

    return Seq(
        *commented_assert(well_formed_burn + valid_pool_xfer),
        pool_bal := pool_asset.holding(Global.current_application_address()).balance(),
        a_bal := a_asset.holding(Global.current_application_address()).balance(),
        b_bal := b_asset.holding(Global.current_application_address()).balance(),
        Assert(
            pool_bal.hasValue(),
            a_bal.hasValue(),
            b_bal.hasValue(),
        ),
        # Get the total number of tokens issued (prior to receiving the current axfer of pool tokens)
        (issued := ScratchVar()).store(
            total_supply_expr - (pool_bal.value() - pool_xfer.get().asset_amount())
        ),
        (a_amt := ScratchVar()).store(
            tokens_to_burn(
                issued.load(),
                a_bal.value(),
                pool_xfer.get().asset_amount(),
            )
        ),
        (b_amt := ScratchVar()).store(
            tokens_to_burn(
                issued.load(),
                b_bal.value(),
                pool_xfer.get().asset_amount(),
            )
        ),
        # Send back commensurate amt of a
        do_axfer(
            Txn.sender(),
            amm_app.state.asset_a,
            a_amt.load(),
        ),
        # Send back commensurate amt of b
        do_axfer(
            Txn.sender(),
            amm_app.state.asset_b,
            b_amt.load(),
        ),
        amm_app.state.ratio.set(compute_ratio()),
    )


@amm_app.external
def swap(
    swap_xfer: abi.AssetTransferTransaction,
    a_asset: abi.Asset = amm_app.state.asset_a,  # type: ignore[assignment]
    b_asset: abi.Asset = amm_app.state.asset_b,  # type: ignore[assignment]
) -> Expr:
    """Swap some amount of either asset A or asset B for the other

    Args:
        swap_xfer: Asset Transfer Transaction of either Asset A or Asset B
        a_asset: Asset ID of asset A so we may inspect balance and possibly transfer it
        b_asset: Asset ID of asset B so we may inspect balance and possibly transfer it
    """
    well_formed_swap = [
        (
            a_asset.asset_id() == amm_app.state.asset_a,
            ConstantProductAMMErrors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == amm_app.state.asset_b,
            ConstantProductAMMErrors.AssetBIncorrect,
        ),
    ]

    valid_swap_xfer = [
        (
            Or(
                swap_xfer.get().xfer_asset() == amm_app.state.asset_a,
                swap_xfer.get().xfer_asset() == amm_app.state.asset_b,
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
        swap_xfer.get().xfer_asset() == amm_app.state.asset_a,
        amm_app.state.asset_b,
        amm_app.state.asset_a,
    )
    in_id = swap_xfer.get().xfer_asset()

    return Seq(
        *commented_assert(well_formed_swap + valid_swap_xfer),
        in_sup := AssetHolding.balance(Global.current_application_address(), in_id),
        out_sup := AssetHolding.balance(Global.current_application_address(), out_id),
        Assert(
            in_sup.hasValue(),
            out_sup.hasValue(),
        ),
        (to_swap := ScratchVar()).store(
            tokens_to_swap(
                swap_xfer.get().asset_amount(),
                in_sup.value() - swap_xfer.get().asset_amount(),
                out_sup.value(),
            )
        ),
        Assert(
            to_swap.load() > Int(0),
            comment=ConstantProductAMMErrors.SendAmountTooLow,
        ),
        do_axfer(
            Txn.sender(),
            out_id,
            to_swap.load(),
        ),
        amm_app.state.ratio.set(compute_ratio()),
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


@Subroutine(TealType.uint64)
def tokens_to_mint(
    issued: Expr, a_supply: Expr, b_supply: Expr, a_amount: Expr, b_amount: Expr
) -> Expr:
    return Seq(
        (a_rat := ScratchVar()).store(WideRatio([a_amount, scale_expr], [a_supply])),
        (b_rat := ScratchVar()).store(WideRatio([b_amount, scale_expr], [b_supply])),
        WideRatio(
            [
                If(a_rat.load() < b_rat.load(), a_rat.load(), b_rat.load()),
                issued,
            ],
            [scale_expr],
        ),
    )


@Subroutine(TealType.uint64)
def tokens_to_mint_initial(a_amount: Expr, b_amount: Expr) -> Expr:
    return Sqrt(a_amount * b_amount) - scale_expr


@Subroutine(TealType.uint64)
def tokens_to_burn(issued: Expr, supply: Expr, amount: Expr) -> Expr:
    return WideRatio([supply, amount], [issued])


@Subroutine(TealType.uint64)
def tokens_to_swap(in_amount: Expr, in_supply: Expr, out_supply: Expr) -> Expr:
    factor = scale_expr - fee_expr
    return WideRatio(
        [in_amount, factor, out_supply],
        [(in_supply * scale_expr) + (in_amount * factor)],
    )


##############
# Utility methods for inner transactions
##############


@Subroutine(TealType.none)
def do_axfer(rx: Expr, aid: Expr, amt: Expr) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: aid,
            TxnField.asset_amount: amt,
            TxnField.asset_receiver: rx,
            TxnField.fee: Int(0),
        }
    )


@Subroutine(TealType.none)
def do_opt_in(aid: Expr) -> Expr:
    return do_axfer(Global.current_application_address(), aid, Int(0))


@Subroutine(TealType.uint64)
def do_create_pool_token(a: Expr, b: Expr) -> Expr:
    return Seq(
        una := AssetParam.unitName(a),
        unb := AssetParam.unitName(b),
        Assert(
            una.hasValue(),
            unb.hasValue(),
        ),
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset_name: Concat(
                    Bytes("DPT-"), una.value(), Bytes("-"), unb.value()
                ),
                TxnField.config_asset_unit_name: Bytes("dpt"),
                TxnField.config_asset_total: total_supply_expr,
                TxnField.config_asset_decimals: Int(3),
                TxnField.config_asset_manager: Global.current_application_address(),
                TxnField.config_asset_reserve: Global.current_application_address(),
                TxnField.fee: Int(0),
            }
        ),
        InnerTxn.created_asset_id(),
    )


@Subroutine(TealType.uint64)
def compute_ratio() -> Expr:
    return Seq(
        bal_a := AssetHolding.balance(
            Global.current_application_address(),
            amm_app.state.asset_a,
        ),
        bal_b := AssetHolding.balance(
            Global.current_application_address(),
            amm_app.state.asset_b,
        ),
        Assert(
            bal_a.hasValue(),
            bal_b.hasValue(),
        ),
        WideRatio([bal_a.value(), scale_expr], [bal_b.value()]),
    )
