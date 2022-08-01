"""
Smart ASA test suite
"""

__author__ = "Cosimo Bassi, Stefano De Angelis"
__email__ = "<cosimo.bassi@algorand.com>, <stefano.deangelis@algorand.com>"

import json
import pprint

from typing import Callable

import pytest

from pyteal import compileTeal, Expr, Int, Mode, Reject, Router

from algosdk.abi import Contract
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.error import AlgodHTTPError
from algosdk.constants import ZERO_ADDRESS
from algosdk.future.transaction import AssetTransferTxn, PaymentTxn

from sandbox import Sandbox
from account import Account, AppAccount

from smart_asa_asc import (
    UNDERLYING_ASA_TOTAL,
    LocalState,
    compile_stateful,
    smart_asa_abi,
)

from smart_asa_client import (
    get_smart_asa_params,
    get_params,
    smart_asa_account_freeze,
    smart_asa_app_create,
    smart_asa_closeout,
    smart_asa_config,
    smart_asa_create,
    smart_asa_destroy,
    smart_asa_freeze,
    smart_asa_get,
    smart_asa_optin,
    smart_asa_transfer,
)

from utils import (
    get_global_state,
    get_local_state,
    get_method,
)

INITIAL_FUNDS = 100_000_000


@pytest.fixture(scope="session")
def smart_asa_abi_router() -> Router:
    print("\n --- Creating Smart ASA ABI...")
    return smart_asa_abi


@pytest.fixture(scope="session")
def pyteal_approval(smart_asa_abi_router: Router) -> Expr:
    approval, _, _ = smart_asa_abi_router.build_program()
    print("\n --- Building Smart ASA PyTeal approval program...")
    return approval


@pytest.fixture(scope="session")
def pyteal_clear(smart_asa_abi_router: Router) -> Expr:
    _, clear, _ = smart_asa_abi_router.build_program()
    print("\n --- Building Smart ASA PyTeal clear program...")
    return clear


@pytest.fixture(scope="session")
def teal_approval(pyteal_approval: Expr) -> str:
    print("\n --- Compiling Smart ASA TEAL approval program...")
    return compile_stateful(pyteal_approval)


@pytest.fixture(scope="session")
def teal_clear(pyteal_clear: Expr) -> str:
    print("\n --- Compiling Smart ASA TEAL clear program...")
    return compile_stateful(pyteal_clear)


@pytest.fixture(scope="session")
def smart_asa_contract(smart_asa_abi_router: Router) -> Contract:
    _, _, contract = smart_asa_abi_router.build_program()
    print("\n --- Building Smart ASA JSON contract...")
    return contract


@pytest.fixture(scope="class")
def creator() -> Account:
    print("\n --- Creator Account...")
    return Sandbox.create(funds_amount=INITIAL_FUNDS)


@pytest.fixture(scope="class")
def eve() -> Account:
    print("\n --- Eve Account...")
    return Sandbox.create(funds_amount=INITIAL_FUNDS)


@pytest.fixture(scope="function")
def smart_asa_app(
    teal_approval: str,
    teal_clear: str,
    creator: Account,
) -> AppAccount:
    app_account = smart_asa_app_create(
        teal_approval=teal_approval,
        teal_clear=teal_clear,
        creator=creator,
    )
    creator.pay(receiver=app_account, amount=1_000_000)
    print("\n --- Creating Smart ASA App...")
    return app_account


@pytest.fixture(
    scope="function",
    params=[False, True],
    ids=["Not Frozen Smart ASA", "Default Frozen Smart ASA"],
)
def smart_asa_id(
    smart_asa_contract: Contract,
    smart_asa_app: AppAccount,
    creator: Account,
    request,
) -> int:
    print("\n --- Creating Smart ASA...")
    return smart_asa_create(
        smart_asa_app=smart_asa_app,
        creator=creator,
        smart_asa_contract=smart_asa_contract,
        total=100,
        metadata_hash=b"XYZXYZ",
        default_frozen=request.param,
    )


@pytest.fixture(scope="function")
def opted_in_creator(
    smart_asa_contract: Contract,
    smart_asa_app: AppAccount,
    creator: Account,
    smart_asa_id: int,
) -> Account:
    print("\n --- Creator opt-in...")
    smart_asa_optin(
        smart_asa_contract=smart_asa_contract,
        smart_asa_app=smart_asa_app,
        asset_id=smart_asa_id,
        caller=creator,
    )
    return creator


@pytest.fixture(scope="function")
def creator_with_supply(
    smart_asa_contract: Contract,
    smart_asa_app: AppAccount,
    opted_in_creator: Account,
    smart_asa_id: int,
) -> Account:
    print("\n --- Minting to Creator...")
    smart_asa_transfer(
        smart_asa_contract=smart_asa_contract,
        smart_asa_app=smart_asa_app,
        xfer_asset=smart_asa_id,
        asset_amount=50,
        caller=opted_in_creator,
        asset_receiver=opted_in_creator,
        asset_sender=smart_asa_app,
    )
    return opted_in_creator


@pytest.fixture(scope="function")
def opted_in_account_factory(
    smart_asa_contract: Contract, smart_asa_app: AppAccount, smart_asa_id: int
) -> Callable:
    def _factory() -> Account:
        account = Sandbox.create(funds_amount=INITIAL_FUNDS)
        smart_asa_optin(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            asset_id=smart_asa_id,
            caller=account,
        )
        print("\n --- Account opt-in...")
        return account

    return _factory


@pytest.fixture(scope="function")
def account_with_supply_factory(
    smart_asa_contract: Contract,
    smart_asa_app: AppAccount,
    smart_asa_id: int,
    creator_with_supply: Account,
    opted_in_account_factory: Callable,
) -> Callable:
    def _factory() -> Account:
        account = opted_in_account_factory()
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=10,
            caller=creator_with_supply,
            asset_receiver=account,
        )
        print("\n --- Minting to Account...")
        return account

    return _factory


def test_compile(
    pyteal_approval: Expr, pyteal_clear: Expr, smart_asa_contract: Contract
) -> None:
    # This test simply ensures we can compile the ASC programs
    teal_approval_program = compile_stateful(pyteal_approval)
    teal_clear_program = compile_stateful(pyteal_clear)

    pprint.pprint("\nABI\n" + json.dumps(smart_asa_contract.dictify()))

    print("\nAPPROVAL PROGRAM\n" + teal_approval_program)
    with open("/tmp/approval.teal", "w") as f:
        f.write(teal_approval_program)

    print("\nCLEAR PROGRAM\n" + teal_clear_program)
    with open("/tmp/clear.teal", "w") as f:
        f.write(teal_clear_program)


class TestAppDeployment:
    def test_wrong_state_schema(
        self,
        teal_approval: str,
        teal_clear: str,
        creator: Account,
    ) -> None:

        with pytest.raises(AlgodHTTPError):
            print("\n --- Creating Smart ASA App with wrong State Schema...")
            creator.create_asc(
                approval_program=teal_approval,
                clear_program=teal_clear,
            )
        print(" --- Rejected as expected!")

    def test_app_create_happy_path(
        self,
        smart_asa_app: AppAccount,
    ) -> None:
        print(f" --- Created Smart ASA App ID: {smart_asa_app.app_id}")

    def test_app_update_fail(self, smart_asa_app: AppAccount, creator: Account) -> None:

        new_approval_program = compileTeal(
            Int(1),
            Mode.Application,
        )
        new_clear_program = compileTeal(Reject(), Mode.Application)

        with pytest.raises(AlgodHTTPError):
            print("\n --- Updating Smart ASA App...")
            creator.update_application(
                approval_program=new_approval_program,
                clear_program=new_clear_program,
                app_id=smart_asa_app.app_id,
            )
        print(" --- Rejected as expected!")

    def test_app_delete_fail(self, smart_asa_app: AppAccount, creator: Account) -> None:
        with pytest.raises(AlgodHTTPError):
            print("\n --- Deleting Smart ASA App...")
            creator.delete_application(smart_asa_app.app_id)
        print(" --- Rejected as expected!")

    def test_app_clear_state_fail(
        self, smart_asa_app: AppAccount, creator: Account
    ) -> None:
        with pytest.raises(AlgodHTTPError):
            print("\n --- Clearing the state of Smart ASA App...")
            creator.clear_state(smart_asa_app.app_id)
        print(" --- Rejected as expected!")


class TestAssetCreate:
    def test_is_not_creator(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        eve: Account,
    ) -> None:

        print("\n --- Creating Smart ASA not with App Creator...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_create(
                smart_asa_app=smart_asa_app,
                creator=eve,
                smart_asa_contract=smart_asa_contract,
                total=100,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    def test_smart_asa_already_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:

        print("\n --- Creating Smart ASA multiple times...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_create(
                smart_asa_app=smart_asa_app,
                creator=creator,
                smart_asa_contract=smart_asa_contract,
                total=100,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:
        print("\n --- Creating Smart ASA...")
        smart_asa_id = smart_asa_create(
            smart_asa_app=smart_asa_app,
            creator=creator,
            smart_asa_contract=smart_asa_contract,
            total=100,
        )
        print(" --- Created Smart ASA ID:", smart_asa_id)

        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["smart_asa_id"] == smart_asa_id
        assert smart_asa["total"] == 100
        assert smart_asa["decimals"] == 0
        assert not smart_asa["default_frozen"]
        assert not smart_asa["unit_name"]
        assert not smart_asa["name"]
        assert not smart_asa["url"]
        assert smart_asa["metadata_hash"][1] == "\x00"
        assert smart_asa["manager_addr"] == creator.address
        assert smart_asa["reserve_addr"] == creator.address
        assert smart_asa["freeze_addr"] == creator.address
        assert smart_asa["clawback_addr"] == creator.address


class TestAssetOptin:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:
        print("\n --- Opt-In App with no Smart ASA ID...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=1,
                caller=creator,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_wrong_smart_asa_id(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        creator.optin_to_asset(smart_asa_id)
        print("\n --- Opt-In App with wrong Smart ASA ID...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id + 1,
                caller=creator,
            )
        print(" --- Rejected as expected!")

    def test_optin_group_wrong_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        wrong_asa = creator.create_asset()
        wrong_asa_txn = AssetTransferTxn(
            sender=creator.address,
            sp=get_params(creator.algod_client),
            receiver=creator.address,
            amt=0,
            index=wrong_asa,
        )
        wrong_asa_txn = TransactionWithSigner(
            txn=wrong_asa_txn,
            signer=creator,
        )
        print("\n --- Opt-In Group with wrong Underlying ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=creator,
                debug_txn=wrong_asa_txn,
            )
        print(" --- Rejected as expected!")

    def test_optin_group_wrong_sender(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        eve.optin_to_asset(smart_asa_id)
        wrong_sender_txn = AssetTransferTxn(
            sender=eve.address,
            sp=get_params(eve.algod_client),
            receiver=creator.address,
            amt=0,
            index=smart_asa_id,
        )
        wrong_sender_txn = TransactionWithSigner(
            txn=wrong_sender_txn,
            signer=eve,
        )
        print("\n --- Opt-In Group with wrong Sender...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=creator,
                debug_txn=wrong_sender_txn,
            )
        print(" --- Rejected as expected!")

    def test_optin_group_wrong_receiver(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        eve.optin_to_asset(smart_asa_id)
        wrong_receiver_txn = AssetTransferTxn(
            sender=creator.address,
            sp=get_params(creator.algod_client),
            receiver=eve.address,
            amt=0,
            index=smart_asa_id,
        )
        wrong_receiver_txn = TransactionWithSigner(
            txn=wrong_receiver_txn,
            signer=creator,
        )
        print("\n --- Opt-In Group with wrong Receiver...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=creator,
                debug_txn=wrong_receiver_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_optin_group_wrong_amount(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:
        wrong_amount_txn = AssetTransferTxn(
            sender=creator_with_supply.address,
            sp=get_params(creator_with_supply.algod_client),
            receiver=creator_with_supply.address,
            amt=1,
            index=smart_asa_id,
        )
        wrong_amount_txn = TransactionWithSigner(
            txn=wrong_amount_txn,
            signer=creator_with_supply,
        )
        print("\n --- Opt-In Group with wrong amount...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=creator_with_supply,
                debug_txn=wrong_amount_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_optin_group_with_asset_close_to(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        wrong_close_to_txn = AssetTransferTxn(
            sender=creator.address,
            sp=get_params(creator.algod_client),
            receiver=creator.address,
            amt=0,
            index=smart_asa_id,
            close_assets_to=smart_asa_app.address,
        )
        wrong_close_to_txn = TransactionWithSigner(
            txn=wrong_close_to_txn,
            signer=creator,
        )
        print("\n --- Opt-In Group with Close Asset To...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_optin(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=creator,
                debug_txn=wrong_close_to_txn,
            )
        print(" --- Rejected as expected!")

    def test_happy_path(
        self,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
    ) -> None:
        smart_asa = get_global_state(
            algod_client=opted_in_creator.algod_client,
            asc_idx=smart_asa_app.app_id,
        )
        local_state = get_local_state(
            algod_client=opted_in_creator.algod_client,
            account_address=opted_in_creator.address,
            asc_idx=smart_asa_app.app_id,
        )
        if smart_asa["default_frozen"]:
            assert local_state["frozen"]
        else:
            assert not local_state["frozen"]


class TestAssetConfig:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:

        wrong_asa = creator.create_asset()

        print("\n --- Configuring unexisting Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            creator.abi_call(
                get_method(smart_asa_contract, "asset_config"),
                wrong_asa,
                100,
                2,
                True,
                "FOO",
                "Foo",
                "foo.spam",
                b"foo",
                creator.address,
                creator.address,
                creator.address,
                creator.address,
                app=smart_asa_app,
                fee=creator.algod_client.suggested_params().fee,
            )
        print(" --- Rejected as expected!")

    def test_is_not_manager(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        # NOTE: This test ensures also that once `manager_add` is set to
        # ZERO_ADDR the Smart ASA can no longer be configured.
        print("\n --- Configuring Smart ASA not with Smart ASA Manager...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_config(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=eve,
                asset_id=smart_asa_id,
                config_manager_addr=ZERO_ADDRESS,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    def test_is_not_correct_smart_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:

        wrong_asa = creator.create_asset()

        print("\n --- Configuring Smart ASA with wrong Asset ID...")
        with pytest.raises(AlgodHTTPError):
            creator.abi_call(
                get_method(smart_asa_contract, "asset_config"),
                wrong_asa,
                100,
                2,
                True,
                "FOO",
                "Foo",
                "foo.spam",
                b"foo",
                creator.address,
                creator.address,
                creator.address,
                creator.address,
                app=smart_asa_app,
                fee=creator.algod_client.suggested_params().fee,
            )
        print(" --- Rejected as expected!")

    def test_disabled_frozen_and_clawback(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        print("\n --- Disabling Smart ASA Freeze and Clawback Addresses...")
        configured_smart_asa_id = smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=creator,
            asset_id=smart_asa_id,
            config_freeze_addr=ZERO_ADDRESS,
            config_clawback_addr=ZERO_ADDRESS,
        )
        print(" --- Configured Smart ASA ID:", configured_smart_asa_id)

        print("\n --- Changing Smart ASA Freeze Address...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_config(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=creator,
                asset_id=smart_asa_id,
                config_freeze_addr=creator,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

        print("\n --- Changing Smart ASA Clawback Address...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_config(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=creator,
                asset_id=smart_asa_id,
                config_clawback_addr=creator,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        eve: Account,
        smart_asa_id: int,
    ) -> None:

        config_s_asa = {
            "smart_asa_id": smart_asa_id,
            "app_id": smart_asa_app.app_id,
            "creator_addr": creator.address,
            "unit_name": "NEW_TEST_!!!",
            "name": "New Test !!!",
            "url": "https://new_test.io",
            "metadata_hash": b"a" * 32,
            "total": 0,
            "decimals": 100,
            "frozen": False,
            "default_frozen": True,
            "manager_addr": eve.address,
            "reserve_addr": eve.address,
            "freeze_addr": eve.address,
            "clawback_addr": eve.address,
        }

        print("\n --- Configuring Smart ASA...")
        configured_smart_asa_id = smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=creator,
            asset_id=smart_asa_id,
            config_total=config_s_asa["total"],
            config_decimals=config_s_asa["decimals"],
            config_default_frozen=config_s_asa["default_frozen"],
            config_unit_name=config_s_asa["unit_name"],
            config_name=config_s_asa["name"],
            config_url=config_s_asa["url"],
            config_metadata_hash=config_s_asa["metadata_hash"],
            config_manager_addr=config_s_asa["manager_addr"],
            config_reserve_addr=config_s_asa["reserve_addr"],
            config_freeze_addr=config_s_asa["freeze_addr"],
            config_clawback_addr=config_s_asa["clawback_addr"],
        )
        print(" --- Configured Smart ASA ID:", configured_smart_asa_id)

        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["smart_asa_id"] == smart_asa_id
        assert smart_asa["total"] == config_s_asa["total"]
        assert smart_asa["decimals"] == config_s_asa["decimals"]
        assert smart_asa["default_frozen"] == config_s_asa["default_frozen"]
        assert smart_asa["unit_name"] == config_s_asa["unit_name"]
        assert smart_asa["name"] == config_s_asa["name"]
        assert smart_asa["url"] == config_s_asa["url"]
        assert smart_asa["metadata_hash"][2:] == config_s_asa["metadata_hash"].decode()
        assert smart_asa["manager_addr"] == config_s_asa["manager_addr"]
        assert smart_asa["reserve_addr"] == config_s_asa["reserve_addr"]
        assert smart_asa["freeze_addr"] == config_s_asa["freeze_addr"]
        assert smart_asa["clawback_addr"] == config_s_asa["clawback_addr"]

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_forbidden_total(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        smart_asa_id: int,
    ) -> None:

        print("\n --- Configuring Smart ASA total...")
        configured_smart_asa_id = smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=opted_in_creator,
            asset_id=smart_asa_id,
            config_total=2,
        )
        print(" --- Configured Smart ASA ID:", configured_smart_asa_id)

        print(
            "\n --- Pre Minting Smart ASA circulating supply:",
            smart_asa_get(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                caller=opted_in_creator,
                asset_id=smart_asa_id,
                getter="get_circulating_supply",
            ),
        )
        print("\n --- Minting Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=2,
            caller=opted_in_creator,
            asset_receiver=opted_in_creator,
            asset_sender=smart_asa_app,
        )
        print(
            "\n --- Post Minting Smart ASA circulating supply:",
            smart_asa_get(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                caller=opted_in_creator,
                asset_id=smart_asa_id,
                getter="get_circulating_supply",
            ),
        )
        assert opted_in_creator.asa_balance(smart_asa_id) == 2

        print("\n --- Configuring forbidden Smart ASA total...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_config(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=opted_in_creator,
                asset_id=smart_asa_id,
                config_total=1,
            )
        print(" --- Rejected as expected!")


class TestAssetTransfer:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:

        print("\n --- Transferring unexisting Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=42,
                asset_amount=100,
                caller=creator,
                asset_receiver=creator,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    def test_is_not_correct_smart_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:

        print("\n --- Transferring Smart ASA with wrong Asset ID...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=42,
                asset_amount=100,
                caller=creator,
                asset_receiver=creator,
                save_abi_call="/tmp/txn.signed",
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_minting_with_wrong_reserve(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        opted_in_account_factory: Callable,
        smart_asa_id: int,
    ) -> None:

        wrong_reserve_account = opted_in_account_factory()
        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)

        print("\n --- Minting Smart ASA with wrong reserve address...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=100,
                caller=wrong_reserve_account,
                asset_receiver=wrong_reserve_account,
                asset_sender=smart_asa_app,
            )
        print(" --- Rejected as expected!")

        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert pre_minting_supply == post_minting_supply

    @pytest.mark.parametrize("smart_asa_id", [True], indirect=True)
    def test_minting_fails_with_frozen_reserve(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        smart_asa_id: int,
    ) -> None:
        creator_state = get_local_state(
            opted_in_creator.algod_client,
            opted_in_creator.address,
            smart_asa_app.app_id,
        )
        assert creator_state["frozen"]

        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)

        print("\n --- Minting Smart ASA with frozen reserve address...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=100,
                caller=opted_in_creator,
                asset_receiver=opted_in_creator,
                asset_sender=smart_asa_app,
            )
        print(" --- Rejected as expected!")

        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert pre_minting_supply == post_minting_supply

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_minting_fails_with_frozen_asset(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        smart_asa_id: int,
    ) -> None:
        smart_asa = get_smart_asa_params(opted_in_creator.algod_client, smart_asa_id)
        assert not smart_asa["frozen"]

        print("\n --- Freezeing whole Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=opted_in_creator,
            freeze_asset=smart_asa_id,
            asset_frozen=True,
        )
        smart_asa = get_smart_asa_params(opted_in_creator.algod_client, smart_asa_id)
        assert smart_asa["frozen"]

        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)

        print("\n --- Minting frozen Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=100,
                caller=opted_in_creator,
                asset_receiver=opted_in_creator,
                asset_sender=smart_asa_app,
            )
        print(" --- Rejected as expected!")

        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert pre_minting_supply == post_minting_supply

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_minting_fails_as_clawback(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        opted_in_account_factory: Callable,
        smart_asa_id: int,
    ) -> None:

        clawback = opted_in_account_factory()

        old_global_state = get_global_state(
            opted_in_creator.algod_client, smart_asa_app.app_id
        )
        assert old_global_state["clawback_addr"] == opted_in_creator.decoded_address

        print("\n --- Configuring clawback in Smart ASA...")
        smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=opted_in_creator,
            asset_id=smart_asa_id,
            config_clawback_addr=clawback,
        )

        new_global_state = get_global_state(
            opted_in_creator.algod_client, smart_asa_app.app_id
        )
        assert new_global_state["clawback_addr"] == clawback.decoded_address

        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)

        print("\n --- Clawbacking Smart ASA from App...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=100,
                caller=clawback,
                asset_receiver=clawback,
                asset_sender=smart_asa_app,
            )
        print(" --- Rejected as expected!")

        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert pre_minting_supply == post_minting_supply

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_happy_path_minting(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        smart_asa_id: int,
    ) -> None:
        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)

        print("\n --- Minting Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=100,
            caller=opted_in_creator,
            asset_receiver=opted_in_creator,
            asset_sender=smart_asa_app,
        )
        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert pre_minting_supply == 0
        assert post_minting_supply == 100
        assert opted_in_creator.asa_balance(smart_asa_id) == 100

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_overminting(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        opted_in_creator: Account,
        smart_asa_id: int,
    ) -> None:
        pre_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Minting Smart ASA circulating supply:", pre_minting_supply)
        print("\n --- Minting Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=100,
            caller=opted_in_creator,
            asset_receiver=opted_in_creator,
            asset_sender=smart_asa_app,
        )
        assert opted_in_creator.asa_balance(smart_asa_id) == 100

        print("\n --- Overminting Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=1,
                caller=opted_in_creator,
                asset_receiver=opted_in_creator,
                asset_sender=smart_asa_app,
            )
        print(" --- Rejected as expected!")
        post_minting_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=opted_in_creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Minting Smart ASA circulating supply:", post_minting_supply)
        assert post_minting_supply == 100

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_burning_fails_with_wrong_reserve(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        opted_in_account_factory: Callable,
        smart_asa_id: int,
    ) -> None:
        wrong_reserve_account = opted_in_account_factory()
        assert creator_with_supply.asa_balance(smart_asa_id) == 50

        pre_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Burning Smart ASA circulating supply:", pre_burning_supply)
        assert pre_burning_supply == 50

        print("\n --- Burning Smart ASA with wrong reserve...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=50,
                caller=wrong_reserve_account,
                asset_receiver=smart_asa_app,
                asset_sender=creator_with_supply,
            )
        print(" --- Rejected as expected!")
        post_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Burning Smart ASA circulating supply:", post_burning_supply)
        assert post_burning_supply == 50

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_burning_fails_with_frozen_reserve(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:
        creator_state = get_local_state(
            creator_with_supply.algod_client,
            creator_with_supply.address,
            smart_asa_app.app_id,
        )
        assert not creator_state["frozen"]
        print("\n --- Freezeing Smart ASA reserve...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator_with_supply,
            freeze_asset=smart_asa_id,
            target_account=creator_with_supply,
            account_frozen=True,
        )
        creator_state = get_local_state(
            creator_with_supply.algod_client,
            creator_with_supply.address,
            smart_asa_app.app_id,
        )
        assert creator_state["frozen"]

        pre_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Burning Smart ASA circulating supply:", pre_burning_supply)

        print("\n --- Burning Smart ASA with frozen reserve...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=50,
                caller=creator_with_supply,
                asset_receiver=smart_asa_app,
                asset_sender=creator_with_supply,
            )
        print(" --- Rejected as expected!")
        post_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Burning Smart ASA circulating supply:", post_burning_supply)
        assert pre_burning_supply == post_burning_supply

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_burning_fails_with_frozen_asset(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:
        smart_asa = get_smart_asa_params(creator_with_supply.algod_client, smart_asa_id)
        assert not smart_asa["frozen"]

        print("\n --- Freezeing whole Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator_with_supply,
            freeze_asset=smart_asa_id,
            asset_frozen=True,
        )
        smart_asa = get_smart_asa_params(creator_with_supply.algod_client, smart_asa_id)
        assert smart_asa["frozen"]

        pre_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Burning Smart ASA circulating supply:", pre_burning_supply)

        print("\n --- Burning frozen Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=50,
                caller=creator_with_supply,
                asset_receiver=smart_asa_app,
                asset_sender=creator_with_supply,
            )
        print(" --- Rejected as expected!")
        post_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Burning Smart ASA circulating supply:", post_burning_supply)
        assert pre_burning_supply == post_burning_supply

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_burning_fails_as_clawback(self, smart_asa_id: int) -> None:
        pass

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_burning_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:

        assert creator_with_supply.asa_balance(smart_asa_id) == 50

        pre_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Pre Burning Smart ASA circulating supply:", pre_burning_supply)
        assert pre_burning_supply == 50

        print("\n --- Burning Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=50,
            caller=creator_with_supply,
            asset_receiver=smart_asa_app,
            asset_sender=creator_with_supply,
        )
        post_burning_supply = smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator_with_supply,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )
        print("\n --- Post Burning Smart ASA circulating supply:", post_burning_supply)
        assert post_burning_supply == 0
        assert smart_asa_app.asa_balance(smart_asa_id) == UNDERLYING_ASA_TOTAL.value

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_receiver_not_optedin_to_app(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        eve.optin_to_asset(smart_asa_id)
        print("\n --- Transferring Smart ASA to not opted-in receiver...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=100,
                caller=creator_with_supply,
                asset_receiver=eve,
                asset_sender=creator_with_supply,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_happy_path_transfer(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        account_with_supply_factory: Callable,
        smart_asa_id: int,
    ) -> None:
        sender = account_with_supply_factory()
        receiver = account_with_supply_factory()
        sender_balance = sender.asa_balance(smart_asa_id)
        receiver_balance = receiver.asa_balance(smart_asa_id)
        amount = 1
        print("\n --- Sender Balance Pre Transfering:", sender_balance)
        print("\n --- Receiver Balance Pre Transfering:", receiver_balance)
        print("\n --- Transferring Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=amount,
            caller=sender,
            asset_receiver=receiver,
        )
        print(
            "\n --- Sender Balance Post Transfering:", sender.asa_balance(smart_asa_id)
        )
        print(
            "\n --- Receiver Balance Post Transfering:",
            receiver.asa_balance(smart_asa_id),
        )
        assert sender.asa_balance(smart_asa_id) == sender_balance - amount
        assert receiver.asa_balance(smart_asa_id) == receiver_balance + amount

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_clawback_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        account_with_supply_factory: Callable,
        smart_asa_id: int,
    ) -> None:
        # NOTE: here we need a `clawback_addr` different from App `creator`
        # otherwise the test falls in `minting` case.
        clawback = account_with_supply_factory()
        revoke_from = account_with_supply_factory()
        receiver = account_with_supply_factory()

        print("\n --- Configuring Smart ASA...")
        smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=creator,
            asset_id=smart_asa_id,
            config_clawback_addr=clawback,
        )

        print("\n --- Clawbacking Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=1,
            caller=clawback,
            asset_sender=revoke_from,
            asset_receiver=receiver,
        )

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_wrong_clawback(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        account_with_supply_factory: Callable,
        smart_asa_id: int,
    ) -> None:
        clawback = account_with_supply_factory()
        revoke_from = account_with_supply_factory()
        receiver = account_with_supply_factory()

        with pytest.raises(AlgodHTTPError):
            print("\n --- Clawbacking Smart ASA with wrong clawback...")
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=1,
                caller=clawback,
                asset_sender=revoke_from,
                asset_receiver=receiver,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_self_clawback_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:
        print("\n --- Self-Clawbacking Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=smart_asa_id,
            asset_amount=1,
            caller=creator_with_supply,
            asset_receiver=creator_with_supply,
        )

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_fail_if_receiver_is_frozen(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        opted_in_account_factory: Callable,
    ) -> None:
        account = opted_in_account_factory()
        account_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        assert not account_state["frozen"]
        print("\n --- Freezeing Smart ASA account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=account,
            account_frozen=True,
        )
        account_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        assert account_state["frozen"]

        amount = 1
        print("\n --- Transferring Smart ASA to freezed account...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=amount,
                caller=creator,
                asset_receiver=account,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_fail_if_sender_is_frozen(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        account_with_supply_factory: Callable,
    ) -> None:
        sender = account_with_supply_factory()
        receiver = account_with_supply_factory()
        sender_state = get_local_state(
            sender.algod_client, sender.address, smart_asa_app.app_id
        )
        assert not sender_state["frozen"]
        print("\n --- Freezeing Smart ASA sender account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=sender,
            account_frozen=True,
        )
        account_state = get_local_state(
            sender.algod_client, sender.address, smart_asa_app.app_id
        )
        assert account_state["frozen"]

        amount = 1
        print("\n --- Transferring Smart ASA from freezed account...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=amount,
                caller=sender,
                asset_receiver=receiver,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_fail_if_smart_asa_is_frozen(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        account_with_supply_factory: Callable,
    ) -> None:
        sender = account_with_supply_factory()
        receiver = account_with_supply_factory()
        sender_state = get_local_state(
            sender.algod_client, sender.address, smart_asa_app.app_id
        )
        receiver_state = get_local_state(
            receiver.algod_client, receiver.address, smart_asa_app.app_id
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert not sender_state["frozen"]
        assert not receiver_state["frozen"]
        assert not smart_asa["frozen"]

        print("\n --- Freezing whole Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            asset_frozen=True,
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["frozen"]

        amount = 1
        print("\n --- Transferring frozen Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=smart_asa_id,
                asset_amount=amount,
                caller=sender,
                asset_receiver=receiver,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_fail_if_not_current_smart_asa_id(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        opted_in_creator: Account,
    ) -> None:

        creator_state = get_local_state(
            opted_in_creator.algod_client,
            opted_in_creator.address,
            smart_asa_app.app_id,
        )

        creator_old_smart_asa_id = creator_state["smart_asa_id"]

        print(f"\n --- Destroying Smart ASA in App {smart_asa_app.app_id}...")
        smart_asa_destroy(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=opted_in_creator,
            destroy_asset=smart_asa_id,
        )
        print(" --- Destroyed Smart ASA ID:", smart_asa_id)

        print(f"\n --- Creating new Smart ASA in App {smart_asa_app.app_id}...")
        new_smart_asa_id = smart_asa_create(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            creator=opted_in_creator,
            total=100,
        )
        print(" --- Created Smart ASA ID:", new_smart_asa_id)

        print(f"\n --- Closing out Smart ASA in App {smart_asa_app.app_id}...")
        smart_asa_closeout(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            asset_id=smart_asa_id,
            caller=opted_in_creator,
            close_to=smart_asa_app,
        )

        print(f"\n --- Creator optin again to Smart ASA App {smart_asa_app.app_id}...")
        smart_asa_optin(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            asset_id=new_smart_asa_id,
            caller=opted_in_creator,
        )

        creator_state = get_local_state(
            opted_in_creator.algod_client,
            opted_in_creator.address,
            smart_asa_app.app_id,
        )
        creator_new_smart_asa_id = creator_state["smart_asa_id"]
        assert creator_old_smart_asa_id != creator_new_smart_asa_id

        print("\n --- Minting Smart ASA...")
        smart_asa_transfer(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            xfer_asset=new_smart_asa_id,
            asset_amount=100,
            caller=opted_in_creator,
            asset_receiver=opted_in_creator,
            asset_sender=smart_asa_app,
        )
        assert opted_in_creator.asa_balance(new_smart_asa_id) == 100

        receiver = Sandbox.create(funds_amount=1_000_000)
        print(f"\n --- Receiver optin to new ASA {new_smart_asa_id}...")
        receiver.optin_to_asset(new_smart_asa_id)

        amount = 1
        print("\n --- Clawbacking new Smart ASA to unauthorized receiver...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=new_smart_asa_id,
                asset_amount=amount,
                caller=opted_in_creator,
                asset_receiver=receiver,
            )
        print(" --- Rejected as expected!")

        print("\n --- Removing clawback from Smart ASA ...")
        smart_asa_config(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=opted_in_creator,
            asset_id=new_smart_asa_id,
            config_clawback_addr=ZERO_ADDRESS,
        )

        print("\n --- Transferring new Smart ASA to unauthorized receiver...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_transfer(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                xfer_asset=new_smart_asa_id,
                asset_amount=amount,
                caller=opted_in_creator,
                asset_receiver=receiver,
            )
        print(" --- Rejected as expected!")


class TestAssetFreeze:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:

        print("\n --- Freezing unexisting Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=creator,
                freeze_asset=42,
                asset_frozen=True,
            )
        print(" --- Rejected as expected!")

    def test_is_not_correct_smart_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:

        print("\n --- Freezing Smart ASA with wrong Asset ID...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=creator,
                freeze_asset=42,
                asset_frozen=True,
            )
        print(" --- Rejected as expected!")

    def test_is_not_freezer(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        with pytest.raises(AlgodHTTPError):
            print("\n --- Unfreezeing whole Smart ASA with wrong account...")
            smart_asa_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=eve,
                freeze_asset=smart_asa_id,
                asset_frozen=False,
            )
        print(" --- Rejected as expected!")

    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert not smart_asa["frozen"]

        print("\n --- Freezeing whole Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            asset_frozen=True,
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["frozen"]

        print("\n --- Unfreezeing whole Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            asset_frozen=False,
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert not smart_asa["frozen"]


class TestAccountFreeze:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        opted_in_account_factory: Callable,
    ) -> None:

        print("\n --- Freezing account for unexisting Smart ASA...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_account_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=creator,
                freeze_asset=42,
                target_account=opted_in_account_factory(),
                account_frozen=True,
            )
        print(" --- Rejected as expected!")

    def test_is_not_correct_smart_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
        opted_in_account_factory: Callable,
    ) -> None:

        print("\n --- Freezing account with wrong Smart ASA ID...")
        with pytest.raises(AlgodHTTPError):
            smart_asa_account_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=creator,
                freeze_asset=42,
                target_account=opted_in_account_factory(),
                account_frozen=True,
            )
        print(" --- Rejected as expected!")

    def test_is_not_freezer(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        with pytest.raises(AlgodHTTPError):
            print("\n --- Unfreezeing account with wrong account...")
            smart_asa_account_freeze(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                freezer=eve,
                freeze_asset=42,
                target_account=eve,
                account_frozen=False,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
        opted_in_account_factory: Callable,
    ) -> None:
        account = opted_in_account_factory()
        account_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        assert not account_state["frozen"]
        print("\n --- Freezeing Smart ASA account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=account,
            account_frozen=True,
        )
        account_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        assert account_state["frozen"]

        print("\n --- Unfreezeing Smart ASA account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=account,
            account_frozen=False,
        )
        account_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        assert not account_state["frozen"]


class TestAssetDestroy:
    def test_smart_asa_not_created(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
    ) -> None:

        with pytest.raises(AlgodHTTPError):
            print("\n --- Destroying unexisting Smart ASA...")
            smart_asa_destroy(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=creator,
                destroy_asset=42,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_is_not_correct_smart_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:

        with pytest.raises(AlgodHTTPError):
            print("\n --- Destroying wrong Smart ASA ID...")
            smart_asa_destroy(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=creator,
                destroy_asset=42,
            )
        print(" --- Rejected as expected!")

    def test_is_not_manager(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        eve: Account,
        smart_asa_id: int,
    ) -> None:
        with pytest.raises(AlgodHTTPError):
            print("\n --- Destroying Smart ASA with wrong account...")
            smart_asa_destroy(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=eve,
                destroy_asset=smart_asa_id,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_smart_asa_still_in_circulation(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator_with_supply: Account,
        smart_asa_id: int,
    ) -> None:
        with pytest.raises(AlgodHTTPError):
            print(
                f"\n --- Destroying circulating Smart ASA in App"
                f" {smart_asa_app.app_id}..."
            )
            smart_asa_destroy(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                manager=creator_with_supply,
                destroy_asset=smart_asa_id,
            )
        print(" --- Rejected as expected!")

    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        creator: Account,
        smart_asa_id: int,
    ) -> None:
        print(f"\n --- Destroying Smart ASA in App {smart_asa_app.app_id}...")
        smart_asa_destroy(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            manager=creator,
            destroy_asset=smart_asa_id,
        )
        print(" --- Destroyed Smart ASA ID:", smart_asa_id)


class TestAssetCloseout:
    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_group_wrong_txn_type(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()

        wrong_type_txn = PaymentTxn(
            sender=account_with_supply.address,
            sp=get_params(account_with_supply.algod_client),
            receiver=account_with_supply.address,
            amt=0,
        )

        wrong_asa_txn = TransactionWithSigner(
            txn=wrong_type_txn,
            signer=account_with_supply,
        )

        with pytest.raises(AlgodHTTPError):
            print("\n --- Close-out Group with wrong Txn Type...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=smart_asa_app,
                debug_txn=wrong_asa_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_group_wrong_asa(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        wrong_asa = account_with_supply.create_asset()
        wrong_asa_txn = AssetTransferTxn(
            sender=account_with_supply.address,
            sp=get_params(account_with_supply.algod_client),
            receiver=account_with_supply.address,
            amt=0,
            index=wrong_asa,
            close_assets_to=smart_asa_app.address,
        )
        wrong_asa_txn = TransactionWithSigner(
            txn=wrong_asa_txn,
            signer=account_with_supply,
        )

        with pytest.raises(AlgodHTTPError):
            print("\n --- Close-out Group with wrong Underlying ASA...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=smart_asa_app,
                debug_txn=wrong_asa_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_group_wrong_sender(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        eve = account_with_supply_factory()

        wrong_sender_txn = AssetTransferTxn(
            sender=eve.address,
            sp=get_params(account_with_supply.algod_client),
            receiver=account_with_supply.address,
            amt=0,
            index=smart_asa_id,
            close_assets_to=smart_asa_app.address,
        )
        wrong_sender_txn = TransactionWithSigner(
            txn=wrong_sender_txn,
            signer=account_with_supply,
        )

        with pytest.raises(AlgodHTTPError):
            print("\n --- Close-out Group with wrong Sender...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=smart_asa_app,
                debug_txn=wrong_sender_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_group_wrong_amount(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()

        wrong_amount_txn = AssetTransferTxn(
            sender=account_with_supply.address,
            sp=get_params(account_with_supply.algod_client),
            receiver=account_with_supply.address,
            amt=10,
            index=smart_asa_id,
            close_assets_to=smart_asa_app.address,
        )
        wrong_amount_txn = TransactionWithSigner(
            txn=wrong_amount_txn,
            signer=account_with_supply,
        )

        with pytest.raises(AlgodHTTPError):
            print("\n --- Close-out Group with wrong Amount...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=smart_asa_app,
                debug_txn=wrong_amount_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_group_with_asset_close_to(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        eve = account_with_supply_factory()

        wrong_closeto_txn = AssetTransferTxn(
            sender=account_with_supply.address,
            sp=get_params(account_with_supply.algod_client),
            receiver=account_with_supply.address,
            amt=0,
            index=smart_asa_id,
            close_assets_to=eve.address,
        )
        wrong_closeto_txn = TransactionWithSigner(
            txn=wrong_closeto_txn,
            signer=account_with_supply,
        )

        with pytest.raises(AlgodHTTPError):
            print("\n --- Close-out Group with wrong Close Asset To...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=smart_asa_app,
                debug_txn=wrong_closeto_txn,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_fails_with_frozen_asset(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        account_with_supply_factory: Callable,
        opted_in_account_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        opted_in_account = opted_in_account_factory()

        print("\n --- Freezeing Smart ASA...")
        smart_asa_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            asset_frozen=True,
        )
        assert get_smart_asa_params(creator.algod_client, smart_asa_id)["frozen"]

        with pytest.raises(AlgodHTTPError):
            print(f"\n --- Closing out frozen asset fails with wrong " f"close to...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=opted_in_account,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_closeout_fails_with_frozen_account(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        account_with_supply_factory: Callable,
        opted_in_account_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        opted_in_account = opted_in_account_factory()

        account_state = get_local_state(
            account_with_supply.algod_client,
            account_with_supply.address,
            smart_asa_app.app_id,
        )
        assert not account_state["frozen"]
        print("\n --- Freezeing Smart ASA account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=account_with_supply,
            account_frozen=True,
        )
        account_state = get_local_state(
            account_with_supply.algod_client,
            account_with_supply.address,
            smart_asa_app.app_id,
        )
        assert account_state["frozen"]

        with pytest.raises(AlgodHTTPError):
            print(f"\n --- Closing out frozen account fails with wrong " f"close to...")
            smart_asa_closeout(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                asset_id=smart_asa_id,
                caller=account_with_supply,
                close_to=opted_in_account,
            )
        print(" --- Rejected as expected!")

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_frozen_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        account_with_supply_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()

        account_state = get_local_state(
            account_with_supply.algod_client,
            account_with_supply.address,
            smart_asa_app.app_id,
        )
        assert not account_state["frozen"]
        print("\n --- Freezeing Smart ASA account...")
        smart_asa_account_freeze(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            freezer=creator,
            freeze_asset=smart_asa_id,
            target_account=account_with_supply,
            account_frozen=True,
        )
        account_state = get_local_state(
            account_with_supply.algod_client,
            account_with_supply.address,
            smart_asa_app.app_id,
        )
        assert account_state["frozen"]

        print(f"\n --- Closing out Smart ASA in App {smart_asa_app.app_id}...")
        smart_asa_closeout(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            asset_id=smart_asa_id,
            caller=account_with_supply,
            close_to=smart_asa_app,
        )
        print(" --- Closed out Smart ASA ID:", smart_asa_id)
        assert not account_with_supply.local_state()

    @pytest.mark.parametrize("smart_asa_id", [False], indirect=True)
    def test_not_frozen_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        account_with_supply_factory: Callable,
        opted_in_account_factory: Callable,
    ) -> None:
        account_with_supply = account_with_supply_factory()
        opted_in_account = opted_in_account_factory()

        print(
            f"\n --- Smart ASA App Local State:\n",
            get_local_state(
                account_with_supply.algod_client,
                account_with_supply.address,
                smart_asa_app.app_id,
            ),
        )
        account_balance = account_with_supply.asa_balance(smart_asa_id)
        print(f"\n --- Closing out Smart ASA in App {smart_asa_app.app_id}...")
        smart_asa_closeout(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            asset_id=smart_asa_id,
            caller=account_with_supply,
            close_to=opted_in_account,
        )
        print(" --- Closed out Smart ASA ID:", smart_asa_id)
        assert not account_with_supply.local_state()
        assert opted_in_account.asa_balance(smart_asa_id) == account_balance


class TestGetters:
    def test_happy_path(
        self,
        smart_asa_contract: Contract,
        smart_asa_app: AppAccount,
        smart_asa_id: int,
        creator: Account,
        opted_in_account_factory: Callable,
    ) -> None:

        print(f"\n --- Getting 'frozen' param of Smart ASA {smart_asa_app.app_id}...")
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["frozen"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="is_asset_frozen",
        )

        account = opted_in_account_factory()
        account_local_state = get_local_state(
            account.algod_client, account.address, smart_asa_app.app_id
        )
        print(f"\n --- Getting 'frozen' param of Account {account.address}...")
        assert account_local_state["frozen"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            account=account,
            getter="is_account_frozen",
        )

        print(f"\n --- Getting 'total' param of Smart ASA {smart_asa_app.app_id}...")
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["total"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_total",
        )

        print(f"\n --- Getting 'decimals' param of Smart ASA {smart_asa_app.app_id}...")
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["decimals"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_decimals",
        )

        print(
            f"\n --- Getting 'unit_name' param of Smart ASA {smart_asa_app.app_id}..."
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["unit_name"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_unit_name",
        )

        print(f"\n --- Getting 'name' param of Smart ASA {smart_asa_app.app_id}...")
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["name"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_asset_name",
        )

        print(f"\n --- Getting 'url' param of Smart ASA {smart_asa_app.app_id}...")
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["url"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_url",
        )

        print(
            f"\n --- Getting 'metadata_hash' param of Smart ASA {smart_asa_app.app_id}..."
        )
        # smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id_with_metadata)
        assert b"XYZXYZ" == bytes(
            smart_asa_get(
                smart_asa_contract=smart_asa_contract,
                smart_asa_app=smart_asa_app,
                caller=creator,
                asset_id=smart_asa_id,
                getter="get_metadata_hash",
            )
        )

        print(
            f"\n --- Getting 'manager_addr' param of Smart ASA {smart_asa_app.app_id}..."
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["manager_addr"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_manager_addr",
        )

        print(
            f"\n --- Getting 'reserve_addr' param of Smart ASA {smart_asa_app.app_id}..."
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["reserve_addr"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_reserve_addr",
        )

        print(
            f"\n --- Getting 'freeze_addr' param of Smart ASA {smart_asa_app.app_id}..."
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["freeze_addr"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_freeze_addr",
        )

        print(
            f"\n --- Getting 'clawback_addr' param of Smart ASA {smart_asa_app.app_id}..."
        )
        smart_asa = get_smart_asa_params(creator.algod_client, smart_asa_id)
        assert smart_asa["clawback_addr"] == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_clawback_addr",
        )

        print(
            f"\n --- Getting 'circulating_supply' of Smart ASA "
            f"{smart_asa_app.app_id}..."
        )
        circulating_supply = UNDERLYING_ASA_TOTAL.value - smart_asa_app.asa_balance(
            smart_asa_id
        )
        assert circulating_supply == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_circulating_supply",
        )

        print(
            f"\n --- Getting 'optin_min_balance' for Smart ASA "
            f"{smart_asa_app.app_id}..."
        )
        optin_min_balance = (
            100_000 + 28_500 * LocalState.num_uints() + 50_000 * LocalState.num_bytes()
        )
        assert optin_min_balance == smart_asa_get(
            smart_asa_contract=smart_asa_contract,
            smart_asa_app=smart_asa_app,
            caller=creator,
            asset_id=smart_asa_id,
            getter="get_optin_min_balance",
        )
