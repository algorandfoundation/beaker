from base64 import b64decode, b64encode
from typing import Any

import algosdk.error
import pyteal as pt
import pytest
from algokit_utils import CallConfig, LogicError, MethodHints
from algosdk.account import generate_account
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
    LogicSigTransactionSigner,
    MultisigTransactionSigner,
)
from algosdk.logic import get_application_address
from algosdk.transaction import LogicSigAccount, Multisig, OnComplete

import beaker
from beaker import (
    Application,
    Authorize,
    BuildOptions,
    GlobalStateValue,
    LocalStateValue,
)
from beaker.application import ABIExternal, _default_argument_from_resolver
from beaker.client.application_client import ApplicationClient
from beaker.sandbox import get_accounts, get_algod_client


class AppState:
    global_state_val_int = GlobalStateValue(pt.TealType.uint64, default=pt.Int(1))
    global_state_val_byte = GlobalStateValue(
        pt.TealType.bytes, default=pt.Bytes("test")
    )
    acct_state_val_int = LocalStateValue(pt.TealType.uint64, default=pt.Int(2))
    acct_state_val_byte = LocalStateValue(
        pt.TealType.bytes, default=pt.Bytes("local-test")
    )


app = Application(
    "App",
    state=AppState(),
    build_options=BuildOptions(avm_version=pt.MAX_PROGRAM_VERSION),
)


@app.create(bare=True)
def create() -> pt.Expr:
    return pt.Seq(
        app.initialize_global_state(),
        pt.Assert(pt.Len(pt.Txn.note()) == pt.Int(0)),
        pt.Approve(),
    )


@app.update(authorize=Authorize.only_creator())
def update() -> pt.Expr:
    return pt.Approve()


@app.delete(authorize=Authorize.only_creator())
def delete() -> pt.Expr:
    return pt.Approve()


@app.opt_in
def opt_in() -> pt.Expr:
    return pt.Seq(
        app.initialize_local_state(),
        pt.Assert(pt.Len(pt.Txn.note()) == pt.Int(0)),
        pt.Approve(),
    )


@app.clear_state
def clear_state() -> pt.Expr:
    return pt.Seq(pt.Assert(pt.Len(pt.Txn.note()) == pt.Int(0)), pt.Approve())


@app.close_out
def close_out() -> pt.Expr:
    return pt.Seq(pt.Assert(pt.Len(pt.Txn.note()) == pt.Int(0)), pt.Approve())


@app.external
def add(a: pt.abi.Uint64, b: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
    return output.set(a.get() + b.get())


@app.external(read_only=True)
def dummy(*, output: pt.abi.String) -> pt.Expr:
    return output.set("deadbeef")


SandboxAccounts = list[tuple[str, str, AccountTransactionSigner]]


@pytest.fixture(scope="session")
def sb_accts() -> SandboxAccounts:
    return [(acct.address, acct.private_key, acct.signer) for acct in get_accounts()]


@pytest.mark.parametrize(
    "deprecated_arg",
    [
        "local_schema",
        "global_schema",
        "approval_program",
        "clear_program",
        "extra_pages",
    ],
)
def test_app_client_call_deprecated(deprecated_arg: str) -> None:
    client = get_algod_client()
    ac = ApplicationClient(client, app)
    with pytest.raises(Exception) as ex:
        args: dict[str, Any] = {deprecated_arg: True}
        ac.call(dummy, **args)

    assert (
        str(ex.value)
        == "Can't create an application using call, either create an application from the "
        "client app_spec using create() or use add_method_call() instead."
    )


def test_app_client_create() -> None:
    client = get_algod_client()
    ac = ApplicationClient(client, app)
    assert ac.signer is None, "Should not have a signer"
    assert ac.sender is None, "Should not have a sender"
    assert ac.app_id == 0, "Should not have app id"
    assert ac.app_addr is None, "Should not have app address"
    assert ac.suggested_params is None, "Should not have suggested params"

    with pytest.raises(Exception):
        ac.get_signer(None)

    with pytest.raises(Exception):
        ac.get_sender(None, None)


def test_app_prepare(sb_accts: SandboxAccounts) -> None:
    client = get_algod_client()

    (addr, sk, signer) = sb_accts[0]

    ac_with_signer = ApplicationClient(client, app, signer=signer)

    assert ac_with_signer.signer == signer, "Should have the same signer"

    assert ac_with_signer.get_signer(None) == signer, "Should produce the same signer"
    assert (
        ac_with_signer.get_sender(None, None) == addr
    ), "Should produce the same address"

    new_pk, new_addr = generate_account()
    new_signer = AccountTransactionSigner(new_pk)
    ac_with_signer_and_sender = ac_with_signer.prepare(sender=new_addr)

    assert (
        ac_with_signer_and_sender.signer == signer
    ), "Should have the same original signer"
    assert (
        ac_with_signer_and_sender.sender == new_addr
    ), "Should have the new addr as sender"

    assert (
        ac_with_signer_and_sender.get_signer(None) == signer
    ), "Should produce the same signer"

    assert (
        ac_with_signer_and_sender.get_sender(None, None) == new_addr
    ), "Should produce the new address"

    assert (
        ac_with_signer_and_sender.get_signer(new_signer) == new_signer
    ), "Should be new signer"
    assert (
        ac_with_signer_and_sender.get_sender(None, new_signer) == new_addr
    ), "Should be new address"

    accts = [generate_account() for _ in range(3)]
    addrs = [acct[1] for acct in accts]
    sks = [acct[0] for acct in accts]

    msig_acct = Multisig(1, 3, addrs)
    msts = MultisigTransactionSigner(msig_acct, sks)

    ac_with_msig = ac_with_signer.prepare(signer=msts)
    assert ac_with_msig.signer == msts, "Should have the same signer"
    assert (
        ac_with_msig.sender == msig_acct.address()
    ), "Should have the address of the msig as the sender"
    assert ac_with_msig.get_signer(None) == msts, "Should produce the same signer"
    assert (
        ac_with_msig.get_sender(None, None) == msig_acct.address()
    ), "Should produce the same address"

    # pragma version 6; int 1; return
    program = b64decode("BoEBQw==")
    lsig = LogicSigAccount(program)
    lsig_signer = LogicSigTransactionSigner(lsig)

    ac_with_lsig = ac_with_signer.prepare(signer=lsig_signer)
    assert ac_with_lsig.signer == lsig_signer, "Should have the same signer"
    assert (
        ac_with_lsig.sender == lsig.address()
    ), "Should have the address of the lsig as the sender"
    assert (
        ac_with_lsig.get_signer(None) == lsig_signer
    ), "Should produce the same signer"
    assert (
        ac_with_lsig.get_sender(None, None) == lsig.address()
    ), "Should produce the same address"

    ac_with_app_id = ac_with_signer.prepare(app_id=3)
    assert (
        ac_with_signer.app_id == 0
    ), "We should not have changed the app id in the original"
    assert (
        ac_with_app_id.app_id == 3
    ), "We should have overwritten the app id in the new version"


def expect_dict(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for k, v in expected.items():
        if type(v) is dict:
            expect_dict(actual[k], v)
        else:
            assert actual[k] == v, f"for field {k}, expected {v} got {actual[k]}"


def test_create(sb_accts: SandboxAccounts) -> None:

    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, app_addr, tx_id = ac.create()
    assert app_id > 0
    assert app_addr == get_application_address(app_id)
    assert ac.app_id == app_id
    assert ac.app_addr == app_addr

    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    assert result_tx["confirmed-round"] > 0
    expect_dict(
        result_tx,
        {
            "application-index": app_id,
            "pool-error": "",
            "txn": {
                "txn": {
                    "snd": addr,
                    "apgs": {"nbs": 1, "nui": 1},
                    "apls": {"nbs": 1, "nui": 1},
                }
            },
        },
    )

    new_addr, new_pk, new_signer = sb_accts[1]
    new_ac = ac.prepare(signer=new_signer)
    extra_pages = 2
    sp = client.suggested_params()
    sp.fee = 1_000_000
    sp.flat_fee = True
    app_id, app_addr, tx_id = new_ac.create(
        extra_pages=extra_pages, suggested_params=sp
    )
    assert app_id > 0
    assert app_addr == get_application_address(app_id)
    assert new_ac.app_id == app_id
    assert new_ac.app_addr == app_addr

    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "application-index": app_id,
            "pool-error": "",
            "txn": {
                "txn": {
                    "snd": new_addr,
                    "apep": extra_pages,
                    "fee": sp.fee,
                    "apgs": {"nbs": 1, "nui": 1},
                    "apls": {"nbs": 1, "nui": 1},
                }
            },
        },
    )

    with pytest.raises(LogicError):
        ac.create(note="failmeplz")


def test_update(sb_accts: SandboxAccounts) -> None:

    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, app_addr, _ = ac.create()

    tx_id = ac.update()
    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apan": OnComplete.UpdateApplicationOC,
                    "apid": app_id,
                    "snd": addr,
                }
            },
        },
    )

    with pytest.raises(LogicError):
        addr, pk, signer2 = sb_accts[1]
        ac2 = ac.prepare(signer=signer2)
        ac2.update()


def test_delete(sb_accts: SandboxAccounts) -> None:
    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, _, _ = ac.create()

    tx_id = ac.delete()
    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apan": OnComplete.DeleteApplicationOC,
                    "apid": app_id,
                    "snd": addr,
                }
            },
        },
    )

    with pytest.raises(LogicError):
        ac = ApplicationClient(client, app, signer=signer)
        app_id, _, _ = ac.create()

        _, _, signer2 = sb_accts[1]
        ac2 = ac.prepare(signer=signer2)
        ac2.delete()


def test_opt_in(sb_accts: SandboxAccounts) -> None:

    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, _, _ = ac.create()

    new_addr, new_pk, new_signer = sb_accts[1]
    new_ac = ac.prepare(signer=new_signer)
    tx_id = new_ac.opt_in()
    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apan": OnComplete.OptInOC,
                    "apid": app_id,
                    "snd": new_addr,
                }
            },
        },
    )

    with pytest.raises(LogicError):
        _, _, newer_signer = sb_accts[2]
        newer_ac = ac.prepare(signer=newer_signer)
        newer_ac.opt_in(note="failmeplz")


def test_close_out(sb_accts: SandboxAccounts) -> None:

    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, _, _ = ac.create()

    new_addr, new_pk, new_signer = sb_accts[1]
    new_ac = ac.prepare(signer=new_signer)
    new_ac.opt_in()

    tx_id = new_ac.close_out()
    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apan": OnComplete.CloseOutOC,
                    "apid": app_id,
                    "snd": new_addr,
                }
            },
        },
    )

    with pytest.raises(LogicError):
        _, _, newer_signer = sb_accts[2]
        newer_ac = ac.prepare(signer=newer_signer)
        newer_ac.opt_in()
        newer_ac.close_out(note="failmeplz")


def test_clear_state(sb_accts: SandboxAccounts) -> None:
    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, app, signer=signer)
    app_id, _, _ = ac.create()

    new_addr, new_pk, new_signer = sb_accts[1]
    new_ac = ac.prepare(signer=new_signer)
    new_ac.opt_in()

    tx_id = new_ac.clear_state()
    result_tx = client.pending_transaction_info(tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apan": OnComplete.ClearStateOC,
                    "apid": app_id,
                    "snd": new_addr,
                }
            },
        },
    )


def test_call(sb_accts: SandboxAccounts) -> None:
    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    app_spec = app.build(client)
    ac = ApplicationClient(client, app_spec, signer=signer)
    app_id, _, _ = ac.create()

    result = ac.call("add", a=1, b=1)
    assert result.return_value == 2
    assert result.decode_error is None
    assert result.raw_value == (2).to_bytes(8, "big")

    method_add = app_spec.contract.get_method_by_name("add")
    raw_args = [
        method_add.get_selector(),
        (1).to_bytes(8, "big"),
        (1).to_bytes(8, "big"),
    ]

    return_prefix = 0x151F7C75
    log_msg = b64encode(
        return_prefix.to_bytes(4, "big") + (2).to_bytes(8, "big")
    ).decode("utf-8")

    result_tx = client.pending_transaction_info(result.tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apaa": [b64encode(arg).decode("utf-8") for arg in raw_args],
                    "apid": app_id,
                    "snd": addr,
                }
            },
            "logs": [log_msg],
        },
    )


def test_add_method_call(sb_accts: SandboxAccounts) -> None:

    addr, pk, signer = sb_accts[0]

    client = get_algod_client()
    app_spec = app.build(client)
    ac = ApplicationClient(client, app_spec, signer=signer)
    app_id, _, _ = ac.create()

    method_add = app_spec.contract.get_method_by_name("add")
    atc = AtomicTransactionComposer()
    ac.add_method_call(atc, method_add, a=1, b=1)
    atc_result = atc.execute(client, 4)
    result = atc_result.abi_results[0]

    assert result.return_value == 2
    assert result.decode_error is None
    assert result.raw_value == (2).to_bytes(8, "big")

    ms = method_add.get_selector()
    raw_args = [ms, (1).to_bytes(8, "big"), (1).to_bytes(8, "big")]

    return_prefix = 0x151F7C75
    log_msg = b64encode(
        return_prefix.to_bytes(4, "big") + (2).to_bytes(8, "big")
    ).decode("utf-8")

    result_tx = client.pending_transaction_info(result.tx_id)
    assert isinstance(result_tx, dict)
    expect_dict(
        result_tx,
        {
            "pool-error": "",
            "txn": {
                "txn": {
                    "apaa": [b64encode(arg).decode("utf-8") for arg in raw_args],
                    "apid": app_id,
                    "snd": addr,
                }
            },
            "logs": [log_msg],
        },
    )


def test_fund(sb_accts: SandboxAccounts) -> None:
    addr, pk, signer = sb_accts[0]
    client = get_algod_client()

    fund_amt = 1_000_000

    ac = ApplicationClient(client, app, signer=signer)
    ac.create()
    ac.fund(fund_amt)

    info = ac.get_application_account_info()
    assert info["amount"] == fund_amt, "Expected balance to equal fund_amt"


def test_default_argument() -> None:
    int_default_argument = {"source": "constant", "data": 1}
    assert _default_argument_from_resolver(pt.Int(1)) == int_default_argument

    string_default_argument = {"source": "constant", "data": "stringy"}
    assert (
        _default_argument_from_resolver(pt.Bytes("stringy")) == string_default_argument
    )

    global_state_int_default_argument = {
        "source": "global-state",
        "data": "global_state_val_int",
    }
    assert (
        _default_argument_from_resolver(app.state.global_state_val_int)
        == global_state_int_default_argument
    )

    global_state_byte_default_argument = {
        "source": "global-state",
        "data": "global_state_val_byte",
    }
    assert (
        _default_argument_from_resolver(app.state.global_state_val_byte)
        == global_state_byte_default_argument
    )

    local_state_int_default_argument = {
        "source": "local-state",
        "data": "acct_state_val_int",
    }
    assert (
        _default_argument_from_resolver(app.state.acct_state_val_int)
        == local_state_int_default_argument
    )

    local_state_byte_default_argument = {
        "source": "local-state",
        "data": "acct_state_val_byte",
    }
    assert (
        _default_argument_from_resolver(app.state.acct_state_val_byte)
        == local_state_byte_default_argument
    )

    method_default_argument = {
        "source": "abi-method",
        "data": {"name": "dummy", "args": [], "returns": {"type": "string"}},
    }
    assert (
        _default_argument_from_resolver(
            ABIExternal(
                actions={"no_op": CallConfig.CALL},
                method=dummy,
                hints=MethodHints(read_only=True),
            )
        )
        == method_default_argument
    )


def test_override_app_create(sb_accts: SandboxAccounts) -> None:
    sc = Application("SpecialCreate")

    @sc.create
    def create(x: pt.abi.Uint64, *, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(x.get())

    sc.build()

    _, _, signer = sb_accts[0]

    client = get_algod_client()
    ac = ApplicationClient(client, sc, signer=signer)

    val = 2

    app_id, _, txid = ac.create(x=val)
    assert app_id > 0

    txinfo = client.pending_transaction_info(txid)
    assert isinstance(txinfo, dict)
    assert txinfo["application-index"] == app_id

    retlog = b64decode(txinfo["logs"][0])
    assert retlog[4:] == val.to_bytes(8, "big")


def test_abi_update(sb_accts: SandboxAccounts) -> None:
    class State:
        app_value = beaker.GlobalStateValue(pt.TealType.uint64)

    app = Application("ABIUpdate", state=State())

    @app.update
    def do_it(x: pt.abi.Uint64) -> pt.Expr:
        return app.state.app_value.set(x.get())

    @app.external
    def get(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(app.state.app_value.get())

    specification = app.build()

    _, _, signer = sb_accts[0]

    client = get_algod_client()
    app_client = ApplicationClient(client, specification, signer=signer)

    app_id, _, _ = app_client.create()

    before = app_client.call("get").return_value

    assert before == 0

    value = 3
    app_client.update(x=value)

    after = app_client.call("get").return_value

    assert after == value


def test_abi_opt_in(sb_accts: SandboxAccounts) -> None:
    class State:
        app_value = beaker.GlobalStateValue(pt.TealType.uint64)

    app = Application("ABIUpdate", state=State())

    @app.opt_in
    def do_it(x: pt.abi.Uint64) -> pt.Expr:
        return app.state.app_value.set(x.get())

    @app.external
    def get(*, output: pt.abi.Uint64) -> pt.Expr:
        return output.set(app.state.app_value.get())

    specification = app.build()

    _, _, signer = sb_accts[0]

    client = get_algod_client()
    app_client = ApplicationClient(client, specification, signer=signer)

    app_id, _, _ = app_client.create()

    before = app_client.call("get").return_value

    assert before == 0

    value = 3
    app_client.opt_in(x=value)

    after = app_client.call("get").return_value

    assert after == value


def test_abi_delete(sb_accts: SandboxAccounts) -> None:
    app = Application("ABIUpdate")

    do_delete = 7

    @app.delete
    def do_it(x: pt.abi.Uint64) -> pt.Expr:
        return pt.If(pt.Eq(x.get(), pt.Int(do_delete)), pt.Approve(), pt.Reject())

    specification = app.build()

    _, _, signer = sb_accts[0]

    client = get_algod_client()
    app_client = ApplicationClient(client, specification, signer=signer)

    app_client.create()

    with pytest.raises(algosdk.error.AlgodHTTPError) as exc_info:
        app_client.delete(x=do_delete + 1)
    assert len(exc_info.value.args) > 0
    exception_message = exc_info.value.args[0]
    assert isinstance(exception_message, str)
    assert exception_message.endswith("transaction rejected by ApprovalProgram"), (
        "Unexpected error: " + exception_message
    )

    app_client.delete(x=do_delete)


def test_abi_close_out(sb_accts: SandboxAccounts) -> None:
    app = Application("ABIUpdate").apply(beaker.unconditional_opt_in_approval)

    do_close_out = 7

    @app.close_out
    def do_it(x: pt.abi.Uint64) -> pt.Expr:
        return pt.If(pt.Eq(x.get(), pt.Int(do_close_out)), pt.Approve(), pt.Reject())

    specification = app.build()

    _, _, signer = sb_accts[0]

    client = get_algod_client()
    app_client = ApplicationClient(client, specification, signer=signer)

    app_client.create()
    app_client.opt_in()

    with pytest.raises(algosdk.error.AlgodHTTPError) as exc_info:
        app_client.close_out(x=do_close_out + 1)
    assert len(exc_info.value.args) > 0
    exception_message = exc_info.value.args[0]
    assert isinstance(exception_message, str)
    assert exception_message.endswith("transaction rejected by ApprovalProgram"), (
        "Unexpected error: " + exception_message
    )

    app_client.close_out(x=do_close_out)
