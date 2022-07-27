from pyteal import Assert, Expr, Global, Gtxn, Seq, Subroutine, TealType


@Subroutine(TealType.none)
def assert_common_checks(idx):
    """Calls all txn checker assert methods

    Note: This doesn't mean the transaction is "safe" but these are common things to check for any transaction
    see https://developer.algorand.org/docs/get-details/dapps/avm/teal/guidelines/ for more details
    """
    return Seq(
        assert_min_fee(idx),
        assert_no_rekey(idx),
        assert_no_close_to(idx),
        assert_no_asset_close_to(idx),
    )


@Subroutine(TealType.none)
def assert_min_fee(idx):
    """Checks that the fee for a transaction is exactly equal to the current min fee"""
    return Assert(Gtxn[idx] == Global.min_txn_fee)


@Subroutine(TealType.none)
def assert_no_rekey(idx) -> Expr:
    """Checks that the rekey_to field is empty, Assert if it is set"""
    return Assert(Gtxn[idx].rekey_to() == Global.zero_address)


@Subroutine(TealType.none)
def assert_no_close_to(idx) -> Expr:
    """Checks that the close_remainder_to field is empty, Assert if it is set"""
    return Assert(Gtxn[idx].close_remainder_to() == Global.zero_address)


@Subroutine(TealType.none)
def assert_no_asset_close_to(idx) -> Expr:
    """Checks that the asset_close_to field is empty, Assert if it is set"""
    return Assert(Gtxn[idx].asset_close_to() == Global.zero_address)
