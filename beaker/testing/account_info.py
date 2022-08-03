from typing import Any
from algosdk.v2client.algod import AlgodClient

def get_balances(client: AlgodClient, accts: list[str]) -> dict[str, dict[int,int]]:
    return {
        acct: balances(client.account_info(acct, exclude='all'))
        for acct in accts
    }

def balances(acct_info: dict[str, Any])-> dict[int, int]:
    """ 
        organize the balances into a dictionary of id=>amount
        0 asset id is algos
    """
    # Init with algos
    b: dict[int,int] = { 0: acct_info['amount'] }
    if 'assets' in acct_info:
        for asset in acct_info['assets']:
            b[asset['asset-id']] = asset['amount']

    return b

def balance_delta(balance_before: dict[int, int], balance_after: dict[int,int]):
    delta: dict[int,int] = {}

    all_ids = list(set(list(balance_before.keys()) + list(balance_after.keys())))

    for aid in all_ids:
        before = balance_before.get(aid, 0)
        after = balance_after.get(aid, 0)
        delta[aid] = after-before

    return delta