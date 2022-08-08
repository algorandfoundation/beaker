"""Module containing helper functions for testing PyTeal Utils."""

from base64 import b64decode
from typing import List, Optional

import algosdk.abi as sdkabi
from algosdk import account, encoding, kmd, logic, mnemonic
from algosdk.future import transaction
from algosdk.v2client import algod, indexer
from pyteal import Cond, Expr, Int, Mode, Seq, Txn, compileTeal

TEAL_VERSION = 5
CLEAR_PROG = bytes([TEAL_VERSION, 129, 1])  # pragma 5; int 1

LOGIC_EVAL_ERROR = "logic eval error"
INVALID_SYNTAX = "invalid syntax"

## Clients


def _algod_client(algod_address="http://localhost:4001", algod_token="a" * 64):
    """Instantiate and return Algod client object."""
    return algod.AlgodClient(algod_token, algod_address)


def _indexer_client(indexer_address="http://localhost:8980", indexer_token="a" * 64):
    """Instantiate and return Indexer client object."""
    return indexer.IndexerClient(indexer_token, indexer_address)


def _kmd_client(kmd_address="http://localhost:4002", kmd_token="a" * 64):
    """Instantiate and return a KMD client object."""
    return kmd.KMDClient(kmd_token, kmd_address)


# Env helpers


class Account:
    def __init__(
        self,
        address: str,
        private_key: Optional[str],
        lsig: Optional[transaction.LogicSig] = None,
        app_id: Optional[int] = None,
    ):
        self.address = address
        self.private_key = private_key
        self.lsig = lsig
        self.app_id = app_id

        assert self.private_key or self.lsig or self.app_id

    def mnemonic(self) -> str:
        return mnemonic.from_private_key(self.private_key)

    def is_lsig(self) -> bool:
        return bool(not self.private_key and not self.app_id and self.lsig)

    def application_address(self) -> str:
        return logic.get_application_address(self.app_id)

    @classmethod
    def create(cls) -> "Account":
        private_key, address = account.generate_account()
        return cls(private_key=private_key, address=str(address))

    @property
    def decoded_address(self):
        return encoding.decode_address(self.address)


def get_kmd_accounts(
    kmd_wallet_name="unencrypted-default-wallet", kmd_wallet_password=""
):
    kmd_client = _kmd_client()
    wallets = kmd_client.list_wallets()

    walletID = None
    for wallet in wallets:
        if wallet["name"] == kmd_wallet_name:
            walletID = wallet["id"]
            break

    if walletID is None:
        raise Exception("Wallet not found: {}".format(kmd_wallet_name))

    walletHandle = kmd_client.init_wallet_handle(walletID, kmd_wallet_password)

    try:
        addresses = kmd_client.list_keys(walletHandle)

        privateKeys = [
            kmd_client.export_key(walletHandle, kmd_wallet_password, addr)
            for addr in addresses
        ]

        kmdAccounts = [
            Account(address=addresses[i], private_key=privateKeys[i])
            for i in range(len(privateKeys))
        ]
    finally:
        kmd_client.release_wallet_handle(walletHandle)

    return kmdAccounts


def sign(signer: Account, txn: transaction.Transaction):
    """Sign a transaction with an Account."""
    if signer.is_lsig():
        return transaction.LogicSigTransaction(txn, signer.lsig)
    else:
        assert signer.private_key
        return txn.sign(signer.private_key)


def sign_send_wait(
    algod_client: algod.AlgodClient,
    signer: Account,
    txn: transaction.Transaction,
    debug=False,
):
    """Sign a transaction, submit it, and wait for its confirmation."""
    signed_txn = sign(signer, txn)
    tx_id = signed_txn.transaction.get_txid()

    if debug:
        transaction.write_to_file([signed_txn], "/tmp/txn.signed", overwrite=True)

    algod_client.send_transactions([signed_txn])
    transaction.wait_for_confirmation(algod_client, tx_id)
    return algod_client.pending_transaction_info(tx_id)


## Teal Helpers

# Create global client to be used in tests
client = _algod_client()


def logged_bytes(b: str):
    return bytes(b, "ascii").hex()


def logged_int(i: int, bits: int = 64):
    return i.to_bytes(bits // 8, "big").hex()


def assert_stateful_output(expr: Expr, output: List[str]):
    assert expr is not None

    src = compile_stateful_app(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    app_id = create_app(
        client,
        compiled["result"],
        transaction.StateSchema(0, 16),
        transaction.StateSchema(0, 64),
    )

    logs, cost, callstack = call_app(client, app_id)
    # print("\nCost: {}, CallStack: {}".format(cost, callstack))
    # print(logs)

    destroy_app(client, app_id)

    assert logs == output


def assert_stateful_fail(expr: Expr, output: List[str]):
    assert expr is not None

    emsg = None

    try:
        src = compile_stateful_app(expr)
        assert len(src) > 0

        compiled = assemble_bytecode(client, src)
        assert len(compiled["hash"]) == 58

        app_id = create_app(
            client,
            compiled["result"],
            transaction.StateSchema(0, 16),
            transaction.StateSchema(0, 64),
        )

        call_app(client, app_id)
    except Exception as e:
        emsg = str(e)

    assert emsg is not None
    assert output.pop() in emsg

    destroy_app(client, app_id)


def assert_output(expr: Expr, output: List[str], **kwargs):
    assert expr is not None

    src = compile_method(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    logs, cost, callstack = execute_app(client, compiled["result"], **kwargs)
    # print("\nCost: {}, CallStack: {}".format(cost, callstack))
    # print(logs)
    assert logs == output


def assert_application_output(expr: Expr, output: List[str], **kwargs):
    assert expr is not None

    src = compile_app(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    logs, cost, callstack = execute_app(client, compiled["result"], **kwargs)
    # print("\nCost: {}, CallStack: {}".format(cost, callstack))
    # print(logs)
    assert logs == output


def assert_close_enough(
    expr: Expr, output: List[float], precisions: List[sdkabi.UfixedType], **kwargs
):
    """assert_close_enough takes some list of floats and corresponding precision and
    asserts that the result from the logic output is close enough to the expected value
    """
    assert expr is not None

    src = compile_method(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    logs, _, _ = execute_app(client, compiled["result"], **kwargs)
    for idx in range(len(output)):
        scale = 10 ** precisions[idx].precision

        incoming = precisions[idx].decode(bytes.fromhex(logs[idx]))
        expected = output[idx] * scale
        max_delta = 2.0  # since we scale the others _up_, we can leave this scaled as 2

        assert (
            abs(expected - incoming) <= max_delta
        ), "Difference greater than max_delta: {} vs {}".format(
            abs(expected - incoming), max_delta
        )


def assert_fail(expr: Expr, output: List[str], **kwargs):
    assert expr is not None

    emsg = None

    try:
        src = compile_method(expr)
        assert len(src) > 0

        compiled = assemble_bytecode(client, src)
        assert len(compiled["hash"]) == 58

        execute_app(client, compiled["result"])
    except Exception as e:
        emsg = str(e)

    assert emsg is not None
    assert output.pop() in emsg


def compile_method(method: Expr, version: int = TEAL_VERSION):
    return compileTeal(Seq(method, Int(1)), mode=Mode.Application, version=version)


def compile_app(application: Expr, version: int = TEAL_VERSION):
    return compileTeal(application, mode=Mode.Application, version=version)


def compile_stateful_app(method: Expr, version: int = TEAL_VERSION):
    expr = Cond(
        [Txn.application_id() == Int(0), Int(1)],
        [Txn.application_args.length() > Int(0), Int(1)],
        [Int(1), Seq(method, Int(1))],
    )
    return compileTeal(expr, mode=Mode.Application, version=version)


def compile_sig(method: Expr, version: int = TEAL_VERSION):
    return compileTeal(
        Seq(method, Int(1)),
        mode=Mode.Signature,
        version=version,
        assembleConstants=True,
    )


def assemble_bytecode(client: algod.AlgodClient, src: str):
    return client.compile(src)


def execute_app(client: algod.AlgodClient, bytecode: str, **kwargs):
    sp = client.suggested_params()

    acct = get_kmd_accounts().pop()

    if "local_schema" not in kwargs:
        kwargs["local_schema"] = transaction.StateSchema(0, 0)

    if "global_schema" not in kwargs:
        kwargs["global_schema"] = transaction.StateSchema(0, 0)

    txns = [
        transaction.ApplicationCallTxn(
            acct.address,
            sp,
            0,
            transaction.OnComplete.DeleteApplicationOC,
            kwargs["local_schema"],
            kwargs["global_schema"],
            b64decode(bytecode),
            CLEAR_PROG,
        )
    ]

    if "pad_budget" in kwargs:
        for i in range(kwargs["pad_budget"]):
            txns.append(
                transaction.ApplicationCallTxn(
                    acct.address,
                    sp,
                    0,
                    transaction.OnComplete.DeleteApplicationOC,
                    kwargs["local_schema"],
                    kwargs["global_schema"],
                    CLEAR_PROG,
                    CLEAR_PROG,
                    note=str(i).encode(),
                )
            )

    txns = [txn.sign(acct.private_key) for txn in transaction.assign_group_id(txns)]
    drr = transaction.create_dryrun(client, txns)

    result = client.dryrun(drr)

    return get_stats_from_dryrun(result)


def get_stats_from_dryrun(dryrun_result):
    logs, cost, trace_len = [], [], []
    txn = dryrun_result["txns"][0]
    raise_rejected(txn)
    if "logs" in txn:
        logs.extend([b64decode(l).hex() for l in txn["logs"]])
    if "cost" in txn:
        cost.append(txn["cost"])
    if "app-call-trace" in txn:
        trace_len.append(len(txn["app-call-trace"]))
    return logs, cost, trace_len


def raise_rejected(txn):
    if "app-call-messages" in txn:
        if "REJECT" in txn["app-call-messages"]:
            raise Exception(txn["app-call-messages"][-1])


def create_app(
    client: algod.AlgodClient,
    bytecode: str,
    local_schema: transaction.StateSchema,
    global_schema: transaction.StateSchema,
    **kwargs
):
    sp = client.suggested_params()

    acct = get_kmd_accounts().pop()

    txn = transaction.ApplicationCallTxn(
        acct.address,
        sp,
        0,
        transaction.OnComplete.NoOpOC,
        local_schema,
        global_schema,
        b64decode(bytecode),
        CLEAR_PROG,
        **kwargs
    )

    txid = client.send_transaction(txn.sign(acct.private_key))
    result = transaction.wait_for_confirmation(client, txid, 3)

    return result["application-index"]


def call_app(client: algod.AlgodClient, app_id: int, **kwargs):
    sp = client.suggested_params()

    acct = get_kmd_accounts().pop()

    txns = transaction.assign_group_id(
        [
            transaction.ApplicationOptInTxn(acct.address, sp, app_id),
            transaction.ApplicationCallTxn(
                acct.address, sp, app_id, transaction.OnComplete.NoOpOC, **kwargs
            ),
            transaction.ApplicationClearStateTxn(acct.address, sp, app_id),
        ]
    )

    drr = transaction.create_dryrun(
        client, [txn.sign(acct.private_key) for txn in txns]
    )
    result = client.dryrun(drr)

    return get_stats_from_dryrun(result)


def destroy_app(client: algod.AlgodClient, app_id: int, **kwargs):
    sp = client.suggested_params()

    acct = get_kmd_accounts().pop()

    txns = transaction.assign_group_id(
        [
            transaction.ApplicationCallTxn(
                acct.address,
                sp,
                app_id,
                transaction.OnComplete.DeleteApplicationOC,
                app_args=["cleanup"],
                **kwargs
            )
        ]
    )

    txid = client.send_transactions([txn.sign(acct.private_key) for txn in txns])

    transaction.wait_for_confirmation(client, txid, 3)
