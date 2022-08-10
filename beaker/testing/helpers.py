"""Module containing helper functions for testing PyTeal Utils."""
from abc import ABC, abstractclassmethod
import pytest
from base64 import b64decode
from typing import List, Optional, Any

import algosdk.abi as sdkabi
from algosdk import account, encoding, logic, mnemonic
from algosdk.future import transaction
from algosdk.v2client import algod
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
)

import pyteal as pt
import beaker as bkr
from beaker.decorators import create


TEAL_VERSION = 5
CLEAR_PROG = bytes([TEAL_VERSION, 129, 1])  # pragma 5; int 1

LOGIC_EVAL_ERROR = "logic eval error"
INVALID_SYNTAX = "invalid syntax"


def logged_bytes(b: str):
    return bytes(b, "ascii").hex()


def logged_int(i: int, bits: int = 64):
    return i.to_bytes(bits // 8, "big").hex()


class UnitTestingApp(bkr.Application):
    @bkr.create
    def create(self):
        return self.app_state.initialize()

    @bkr.delete
    def delete(self):
        return pt.Approve()

    @bkr.update
    def update(self):
        return pt.Approve()

    @bkr.opt_in
    def opt_in(self):
        return self.acct_state.initialize()

    @bkr.external
    def opup(self):
        return pt.Approve()

    @bkr.external
    def unit_test(self):
        # Implement this method
        pass


class TestAccount:
    def __init__(
        self,
        address: str,
        private_key: Optional[str],
        lsig: Optional[transaction.LogicSig] = None,
        app_id: Optional[int] = None,
    ):
        self.address = address
        self.private_key = private_key
        self.signer = AccountTransactionSigner(private_key)
        self.lsig = lsig
        self.app_id = app_id

        assert self.private_key or self.lsig or self.app_id

    def mnemonic(self) -> str:
        return mnemonic.from_private_key(self.private_key)

    def is_lsig(self) -> bool:
        return bool(not self.private_key and not self.app_id and self.lsig)

    def application_address(self) -> str:
        return logic.get_application_address(self.app_id)

    def sign(self, txn: transaction.Transaction):
        """Sign a transaction with an TestAccount."""
        if self.is_lsig():
            return transaction.LogicSigTransaction(txn, self.lsig)
        else:
            assert self.private_key
            return txn.sign(self.private_key)

    @classmethod
    def create(cls) -> "TestAccount":
        private_key, address = account.generate_account()
        return cls(private_key=private_key, address=str(address))

    @property
    def decoded_address(self):
        return encoding.decode_address(self.address)


client = bkr.sandbox.get_algod_client()
accounts = [
    TestAccount(acct.address, acct.private_key) for acct in bkr.sandbox.get_accounts()
]


def assert_abi_output(
    app: UnitTestingApp,
    inputs: list[dict[str, Any]],
    outputs: list[Any],
    opups: int = 0,
):
    app_client = bkr.client.ApplicationClient(client, app, signer=accounts[0].signer)
    app_client.create()

    if app.acct_state.num_byte_slices > 0 or app.acct_state.num_uints > 0:
        app_client.opt_in()

    for idx, output in enumerate(outputs):
        input = {} if len(inputs) == 0 else inputs[idx]

        if opups > 0:
            atc = AtomicTransactionComposer()

            app_client.add_method_call(atc, app.unit_test, **input)
            for x in range(opups):
                app_client.add_method_call(atc, app.opup, note=str(x).encode())

            try:
                results = atc.execute(client, 2)
            except Exception as e:
                raise app_client.wrap_approval_exception(e)

            assert results.abi_results[0].return_value == output
        else:
            result = app_client.call(app.unit_test, **input)
            # print(result.return_value, output)
            assert result.return_value == output

    app_client.delete()


## Teal Helpers
def assert_stateful_output(expr: pt.Expr, output: List[str]):
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

    logs, _, _ = call_app(client, app_id)

    destroy_app(client, app_id)

    assert logs == output


def assert_stateful_fail(expr: pt.Expr, output: List[str]):
    assert expr is not None

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


def assert_output(expr: pt.Expr, output: List[str], **kwargs):
    assert expr is not None

    src = compile_method(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    logs, _, _ = execute_app(client, compiled["result"], **kwargs)
    assert logs == output


def assert_application_output(expr: pt.Expr, output: List[str], **kwargs):
    assert expr is not None

    src = compile_app(expr)
    assert len(src) > 0

    compiled = assemble_bytecode(client, src)
    assert len(compiled["hash"]) == 58

    logs, _, _ = execute_app(client, compiled["result"], **kwargs)
    assert logs == output


def assert_close_enough(
    expr: pt.Expr, output: List[float], precisions: List[sdkabi.UfixedType], **kwargs
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


def assert_fail(expr: pt.Expr, output: List[str], **kwargs):
    assert expr is not None
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


def compile_method(method: pt.Expr, version: int = TEAL_VERSION):
    return pt.compileTeal(
        pt.Seq(method, pt.Int(1)), mode=pt.Mode.Application, version=version
    )


def compile_stateful_app(method: pt.Expr, version: int = TEAL_VERSION) -> str:
    return compile_app(
        pt.Cond(
            [pt.Txn.application_id() == pt.Int(0), pt.Approve()],
            [pt.Txn.on_completion() == pt.OnComplete.UpdateApplication, pt.Approve()],
            [pt.Txn.on_completion() == pt.OnComplete.DeleteApplication, pt.Approve()],
            # for budget padding
            [pt.Txn.application_args.length() > pt.Int(0), pt.Approve()],
            # handle the actual method
            [pt.Int(1), pt.Seq(method, pt.Approve())],
        ),
        version=version,
    )


def compile_app(application: pt.Expr, version: int = TEAL_VERSION):
    return pt.compileTeal(application, mode=pt.Mode.Application, version=version)


def compile_sig(method: pt.Expr, version: int = TEAL_VERSION):
    return pt.compileTeal(
        pt.Seq(method, pt.Int(1)),
        mode=pt.Mode.Signature,
        version=version,
        assembleConstants=True,
    )


def assemble_bytecode(client: algod.AlgodClient, src: str):
    return client.compile(src)


def execute_app(
    client: algod.AlgodClient, bytecode: str, pad_budget: int = 0, **kwargs
) -> tuple[list[str], Any, Any]:
    sp = client.suggested_params()

    acct = bkr.sandbox.get_accounts()[0]

    if "local_schema" not in kwargs:
        kwargs["local_schema"] = transaction.StateSchema(0, 0)

    if "global_schema" not in kwargs:
        kwargs["global_schema"] = transaction.StateSchema(0, 0)

    txns: list[transaction.Transaction] = transaction.assign_group_id(
        [
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
        + [
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
            for i in range(pad_budget)
        ]
    )

    # First tx id is the only one we care about
    txid = client.send_transactions([txn.sign(acct.private_key) for txn in txns])
    return get_stats_from_result(transaction.wait_for_confirmation(client, txid))

    # TODO: once we have simulate, maybe use that
    # drr = transaction.create_dryrun(
    #    client, [txn.sign(acct.private_key) for txn in txns]
    # )
    # return get_stats_from_dryrun(client.dryrun(drr))


def get_stats_from_result(
    result: dict[str, Any]
) -> tuple[list[str], list[int], list[int]]:
    logs, cost, trace_len = [], [0], [0]
    if "logs" in result:
        logs.extend([b64decode(l).hex() for l in result["logs"]])
    return logs, cost, trace_len


def get_stats_from_dryrun(dryrun_result) -> tuple[list[str], list[int], list[int]]:
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

    acct = accounts[0]

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

    acct = accounts[0]

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

    acct = accounts[0]

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
