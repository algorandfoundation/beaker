import pyteal as pt

import beaker

# WARNING: This code is provided for example only. Do NOT deploy to mainnet.

pt.pragma(compiler_version="^0.23.0")


def commented_assert(conditions: list[tuple[pt.Expr, str]]) -> list[pt.Expr]:
    return [pt.Assert(cond, comment=cmt) for cond, cmt in conditions]


##############
# Constants
##############
class Errors:
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


# Total supply of the pool tokens
TOTAL_SUPPLY = int(1e10)
TOTAL_SUPPLY_EXPR = pt.Int(TOTAL_SUPPLY)
# scale helps with precision when doing computation for
# the number of tokens to transfer
SCALE = 1000
SCALE_EXPR = pt.Int(SCALE)
# Fee for swaps, 5 represents 0.5% ((fee / scale)*100)
FEE = 5
FEE_EXPR = pt.Int(FEE)


class ConstantProductAMMState:
    asset_a = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        key="a",
        static=True,
        descr="The asset id of asset A",
    )
    asset_b = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        key="b",
        static=True,
        descr="The asset id of asset B",
    )
    governor = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
        key="g",
        default=pt.Global.creator_address(),
        descr="The current governor of this contract, allowed to do admin type actions",
    )
    pool_token = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        key="p",
        static=True,
        descr="The asset id of the Pool Token, "
        "used to track share of pool the holder may recover",
    )
    ratio = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64,
        key="r",
        descr="The ratio between assets (A/B)*Scale",
    )


app = (
    beaker.Application("ConstantProductAMM", state=ConstantProductAMMState())
    # On create, init app state
    .apply(beaker.unconditional_create_approval, initialize_global_state=True)
)


# Only the account set in global_state.governor may call this method
@app.external(authorize=beaker.Authorize.only(app.state.governor))
def set_governor(new_governor: pt.abi.Account) -> pt.Expr:
    """sets the governor of the contract, may only be called by the current governor"""
    return app.state.governor.set(new_governor.address())


# Only the account set in global_state.governor may call this method
@app.external(authorize=beaker.Authorize.only(app.state.governor))
def bootstrap(
    seed: pt.abi.PaymentTransaction,
    a_asset: pt.abi.Asset,
    b_asset: pt.abi.Asset,
    *,
    output: pt.abi.Uint64,
) -> pt.Expr:
    """bootstraps the contract by opting into the assets and creating the pool token.

    Note this method will fail if it is attempted more than once on the same contract
    since the assets and pool token application state values are marked as static and
    cannot be overridden.

    Args:
        seed: Initial Payment transaction to the app account so it can opt in to assets
            and create pool token.
        a_asset: One of the two assets this pool should allow swapping between.
        b_asset: The other of the two assets this pool should allow swapping between.

    Returns:
        The asset id of the pool token created.
    """

    well_formed_bootstrap = [
        (pt.Global.group_size() == pt.Int(2), Errors.GroupSizeNot2),
        (
            seed.get().receiver() == pt.Global.current_application_address(),
            Errors.ReceiverNotAppAddr,
        ),
        (
            seed.get().amount() >= beaker.consts.Algos(0.3),
            Errors.AmountLessThanMinimum,
        ),
        (
            a_asset.asset_id() < b_asset.asset_id(),
            Errors.AssetIdsIncorrect,
        ),
    ]

    return pt.Seq(
        *commented_assert(well_formed_bootstrap),
        app.state.asset_a.set(a_asset.asset_id()),
        app.state.asset_b.set(b_asset.asset_id()),
        app.state.pool_token.set(
            do_create_pool_token(
                app.state.asset_a,
                app.state.asset_b,
            ),
        ),
        do_opt_in(app.state.asset_a),
        do_opt_in(app.state.asset_b),
        output.set(app.state.pool_token),
    )


##############
# AMM specific methods for mint/burn/swap
##############


@app.external
def mint(
    a_xfer: pt.abi.AssetTransferTransaction,
    b_xfer: pt.abi.AssetTransferTransaction,
    pool_asset: pt.abi.Asset = app.state.pool_token,  # type: ignore[assignment]
    a_asset: pt.abi.Asset = app.state.asset_a,  # type: ignore[assignment]
    b_asset: pt.abi.Asset = app.state.asset_b,  # type: ignore[assignment]
) -> pt.Expr:
    """mint pool tokens given some amount of asset A and asset B.

    Given some amount of Asset A and Asset B in the transfers, mint some number of pool
    tokens commensurate with the pools current balance and circulating supply of
    pool tokens.

    Args:
        a_xfer: Asset Transfer Transaction of asset A as a deposit to the pool in
            exchange for pool tokens.
        b_xfer: Asset Transfer Transaction of asset B as a deposit to the pool in
            exchange for pool tokens.
        pool_asset: The asset ID of the pool token so that we may distribute it.
        a_asset: The asset ID of the Asset A so that we may inspect our balance.
        b_asset: The asset ID of the Asset B so that we may inspect our balance.
    """

    well_formed_mint = [
        (
            a_asset.asset_id() == app.state.asset_a,
            Errors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == app.state.asset_b,
            Errors.AssetBIncorrect,
        ),
        (
            pool_asset.asset_id() == app.state.pool_token,
            Errors.AssetPoolIncorrect,
        ),
        (
            pt.And(
                a_xfer.get().sender() == pt.Txn.sender(),
                b_xfer.get().sender() == pt.Txn.sender(),
            ),
            Errors.SenderInvalid,
        ),
    ]

    valid_asset_a_xfer = [
        (
            a_xfer.get().asset_receiver() == pt.Global.current_application_address(),
            Errors.ReceiverNotAppAddr,
        ),
        (
            a_xfer.get().xfer_asset() == app.state.asset_a,
            Errors.AssetAIncorrect,
        ),
        (
            a_xfer.get().asset_amount() > pt.Int(0),
            Errors.AmountLessThanMinimum,
        ),
    ]

    valid_asset_b_xfer = [
        (
            b_xfer.get().asset_receiver() == pt.Global.current_application_address(),
            Errors.ReceiverNotAppAddr,
        ),
        (
            b_xfer.get().xfer_asset() == app.state.asset_b,
            Errors.AssetBIncorrect,
        ),
        (
            b_xfer.get().asset_amount() > pt.Int(0),
            Errors.AmountLessThanMinimum,
        ),
    ]

    return pt.Seq(
        # Check that the transaction is constructed correctly
        *commented_assert(well_formed_mint + valid_asset_a_xfer + valid_asset_b_xfer),
        # Check that we have these things
        pool_bal := pool_asset.holding(
            pt.Global.current_application_address()
        ).balance(),
        a_bal := a_asset.holding(pt.Global.current_application_address()).balance(),
        b_bal := b_asset.holding(pt.Global.current_application_address()).balance(),
        pt.Assert(
            pool_bal.hasValue(),
            a_bal.hasValue(),
            b_bal.hasValue(),
        ),
        (to_mint := pt.ScratchVar()).store(
            pt.If(
                pt.And(
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
                    TOTAL_SUPPLY_EXPR - pool_bal.value(),
                    a_bal.value() - a_xfer.get().asset_amount(),
                    b_bal.value() - b_xfer.get().asset_amount(),
                    a_xfer.get().asset_amount(),
                    b_xfer.get().asset_amount(),
                ),
            )
        ),
        pt.Assert(
            to_mint.load() > pt.Int(0),
            comment=Errors.SendAmountTooLow,
        ),
        # mint tokens
        do_axfer(pt.Txn.sender(), app.state.pool_token, to_mint.load()),
        app.state.ratio.set(compute_ratio()),
    )


@app.external
def burn(
    pool_xfer: pt.abi.AssetTransferTransaction,
    pool_asset: pt.abi.Asset = app.state.pool_token,  # type: ignore[assignment]
    a_asset: pt.abi.Asset = app.state.asset_a,  # type: ignore[assignment]
    b_asset: pt.abi.Asset = app.state.asset_b,  # type: ignore[assignment]
) -> pt.Expr:
    """burn pool tokens to get back some amount of asset A and asset B

    Args:
        pool_xfer: Asset Transfer Transaction of the pool token for the amount the
            sender wishes to redeem
        pool_asset: Asset ID of the pool token so we may inspect balance.
        a_asset: Asset ID of Asset A so we may inspect balance and distribute it
        b_asset: Asset ID of Asset B so we may inspect balance and distribute it
    """

    well_formed_burn = [
        (
            pool_asset.asset_id() == app.state.pool_token,
            Errors.AssetPoolIncorrect,
        ),
        (
            a_asset.asset_id() == app.state.asset_a,
            Errors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == app.state.asset_b,
            Errors.AssetBIncorrect,
        ),
    ]

    valid_pool_xfer = [
        (
            pool_xfer.get().asset_receiver() == pt.Global.current_application_address(),
            Errors.ReceiverNotAppAddr,
        ),
        (
            pool_xfer.get().asset_amount() > pt.Int(0),
            Errors.AmountLessThanMinimum,
        ),
        (
            pool_xfer.get().xfer_asset() == app.state.pool_token,
            Errors.AssetPoolIncorrect,
        ),
        (
            pool_xfer.get().sender() == pt.Txn.sender(),
            Errors.SenderInvalid,
        ),
    ]

    return pt.Seq(
        *commented_assert(well_formed_burn + valid_pool_xfer),
        pool_bal := pool_asset.holding(
            pt.Global.current_application_address()
        ).balance(),
        a_bal := a_asset.holding(pt.Global.current_application_address()).balance(),
        b_bal := b_asset.holding(pt.Global.current_application_address()).balance(),
        pt.Assert(
            pool_bal.hasValue(),
            a_bal.hasValue(),
            b_bal.hasValue(),
        ),
        # Get the total number of tokens issued
        # !important: this happens prior to receiving the current axfer of pool tokens
        (issued := pt.ScratchVar()).store(
            TOTAL_SUPPLY_EXPR - (pool_bal.value() - pool_xfer.get().asset_amount())
        ),
        (a_amt := pt.ScratchVar()).store(
            tokens_to_burn(
                issued.load(),
                a_bal.value(),
                pool_xfer.get().asset_amount(),
            )
        ),
        (b_amt := pt.ScratchVar()).store(
            tokens_to_burn(
                issued.load(),
                b_bal.value(),
                pool_xfer.get().asset_amount(),
            )
        ),
        # Send back commensurate amt of a
        do_axfer(
            pt.Txn.sender(),
            app.state.asset_a,
            a_amt.load(),
        ),
        # Send back commensurate amt of b
        do_axfer(
            pt.Txn.sender(),
            app.state.asset_b,
            b_amt.load(),
        ),
        app.state.ratio.set(compute_ratio()),
    )


@app.external
def swap(
    swap_xfer: pt.abi.AssetTransferTransaction,
    a_asset: pt.abi.Asset = app.state.asset_a,  # type: ignore[assignment]
    b_asset: pt.abi.Asset = app.state.asset_b,  # type: ignore[assignment]
) -> pt.Expr:
    """Swap some amount of either asset A or asset B for the other

    Args:
        swap_xfer: Asset Transfer Transaction of either Asset A or Asset B
        a_asset: Asset ID of asset A so we may inspect balance and possibly transfer it
        b_asset: Asset ID of asset B so we may inspect balance and possibly transfer it
    """
    well_formed_swap = [
        (
            a_asset.asset_id() == app.state.asset_a,
            Errors.AssetAIncorrect,
        ),
        (
            b_asset.asset_id() == app.state.asset_b,
            Errors.AssetBIncorrect,
        ),
    ]

    valid_swap_xfer = [
        (
            pt.Or(
                swap_xfer.get().xfer_asset() == app.state.asset_a,
                swap_xfer.get().xfer_asset() == app.state.asset_b,
            ),
            Errors.AssetIdsIncorrect,
        ),
        (
            swap_xfer.get().asset_amount() > pt.Int(0),
            Errors.AmountLessThanMinimum,
        ),
        (
            swap_xfer.get().sender() == pt.Txn.sender(),
            Errors.SenderInvalid,
        ),
    ]

    out_id = pt.If(
        swap_xfer.get().xfer_asset() == app.state.asset_a,
        app.state.asset_b,
        app.state.asset_a,
    )
    in_id = swap_xfer.get().xfer_asset()

    return pt.Seq(
        *commented_assert(well_formed_swap + valid_swap_xfer),
        in_sup := pt.AssetHolding.balance(
            pt.Global.current_application_address(), in_id
        ),
        out_sup := pt.AssetHolding.balance(
            pt.Global.current_application_address(), out_id
        ),
        pt.Assert(
            in_sup.hasValue(),
            out_sup.hasValue(),
        ),
        (to_swap := pt.ScratchVar()).store(
            tokens_to_swap(
                swap_xfer.get().asset_amount(),
                in_sup.value() - swap_xfer.get().asset_amount(),
                out_sup.value(),
            )
        ),
        pt.Assert(
            to_swap.load() > pt.Int(0),
            comment=Errors.SendAmountTooLow,
        ),
        do_axfer(
            pt.Txn.sender(),
            out_id,
            to_swap.load(),
        ),
        app.state.ratio.set(compute_ratio()),
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


@pt.Subroutine(pt.TealType.uint64)
def tokens_to_mint(
    issued: pt.Expr,
    a_supply: pt.Expr,
    b_supply: pt.Expr,
    a_amount: pt.Expr,
    b_amount: pt.Expr,
) -> pt.Expr:
    return pt.Seq(
        (a_rat := pt.ScratchVar()).store(
            pt.WideRatio([a_amount, SCALE_EXPR], [a_supply])
        ),
        (b_rat := pt.ScratchVar()).store(
            pt.WideRatio([b_amount, SCALE_EXPR], [b_supply])
        ),
        pt.WideRatio(
            [
                pt.If(a_rat.load() < b_rat.load(), a_rat.load(), b_rat.load()),
                issued,
            ],
            [SCALE_EXPR],
        ),
    )


@pt.Subroutine(pt.TealType.uint64)
def tokens_to_mint_initial(a_amount: pt.Expr, b_amount: pt.Expr) -> pt.Expr:
    return pt.Sqrt(a_amount * b_amount) - SCALE_EXPR


@pt.Subroutine(pt.TealType.uint64)
def tokens_to_burn(issued: pt.Expr, supply: pt.Expr, amount: pt.Expr) -> pt.Expr:
    return pt.WideRatio([supply, amount], [issued])


@pt.Subroutine(pt.TealType.uint64)
def tokens_to_swap(
    in_amount: pt.Expr, in_supply: pt.Expr, out_supply: pt.Expr
) -> pt.Expr:
    factor = SCALE_EXPR - FEE_EXPR
    return pt.WideRatio(
        [in_amount, factor, out_supply],
        [(in_supply * SCALE_EXPR) + (in_amount * factor)],
    )


##############
# Utility methods for inner transactions
##############


@pt.Subroutine(pt.TealType.none)
def do_axfer(rx: pt.Expr, aid: pt.Expr, amt: pt.Expr) -> pt.Expr:
    return pt.InnerTxnBuilder.Execute(
        {
            pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
            pt.TxnField.xfer_asset: aid,
            pt.TxnField.asset_amount: amt,
            pt.TxnField.asset_receiver: rx,
            pt.TxnField.fee: pt.Int(0),
        }
    )


@pt.Subroutine(pt.TealType.none)
def do_opt_in(aid: pt.Expr) -> pt.Expr:
    return do_axfer(pt.Global.current_application_address(), aid, pt.Int(0))


@pt.Subroutine(pt.TealType.uint64)
def do_create_pool_token(a: pt.Expr, b: pt.Expr) -> pt.Expr:
    return pt.Seq(
        una := pt.AssetParam.unitName(a),
        unb := pt.AssetParam.unitName(b),
        pt.Assert(
            una.hasValue(),
            unb.hasValue(),
        ),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetConfig,
                pt.TxnField.config_asset_name: pt.Concat(
                    pt.Bytes("DPT-"), una.value(), pt.Bytes("-"), unb.value()
                ),
                pt.TxnField.config_asset_unit_name: pt.Bytes("dpt"),
                pt.TxnField.config_asset_total: TOTAL_SUPPLY_EXPR,
                pt.TxnField.config_asset_decimals: pt.Int(3),
                pt.TxnField.config_asset_manager: pt.Global.current_application_address(),
                pt.TxnField.config_asset_reserve: pt.Global.current_application_address(),
                pt.TxnField.fee: pt.Int(0),
            }
        ),
        pt.InnerTxn.created_asset_id(),
    )


@pt.Subroutine(pt.TealType.uint64)
def compute_ratio() -> pt.Expr:
    return pt.Seq(
        bal_a := pt.AssetHolding.balance(
            pt.Global.current_application_address(),
            app.state.asset_a,
        ),
        bal_b := pt.AssetHolding.balance(
            pt.Global.current_application_address(),
            app.state.asset_b,
        ),
        pt.Assert(
            bal_a.hasValue(),
            bal_b.hasValue(),
        ),
        pt.WideRatio([bal_a.value(), SCALE_EXPR], [bal_b.value()]),
    )
