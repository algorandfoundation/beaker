from typing import Any
from algosdk.v2client.algod import AlgodClient


def get_balances(client: AlgodClient, accts: list[str]) -> dict[str, dict[int, int]]:
    """get the balances for all the accounts in the list passed"""
    return {acct: balances(client.account_info(acct)) for acct in accts}


def get_deltas(
    acct_balances_before: dict[str, dict[int, int]],
    acct_balances_after: dict[str, dict[int, int]],
) -> dict[str, dict[int, int]]:
    """get the difference between the balances before and after some event"""
    return {
        acct: balance_delta(acct_balances_before[acct], acct_balances_after[acct])
        for acct in acct_balances_after.keys()
    }


def balances(acct_info: dict[str, Any]) -> dict[int, int]:
    """organize the balances into a dictionary of id=>amount

    Note:
        0 asset id is algos

    """
    # Init with 0 for algos
    b: dict[int, int] = {0: acct_info["amount"]}
    if "assets" in acct_info:
        for asset in acct_info["assets"]:
            b[asset["asset-id"]] = asset["amount"]

    return b


def balance_delta(
    balance_before: dict[int, int], balance_after: dict[int, int]
) -> dict[int, int]:
    """take the difference between balance after and before"""

    all_ids = list(set(list(balance_before.keys()) + list(balance_after.keys())))

    return {
        aid: balance_after.get(aid, 0) - balance_before.get(aid, 0) for aid in all_ids
    }
