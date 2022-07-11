from base64 import b64decode
from math import ceil
from typing import Any, cast

from algosdk.account import address_from_private_key
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
    AtomicTransactionResponse,
    TransactionWithSigner,
    abi,
)
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from pyteal import ABIReturnSubroutine

from beaker.application import Application, method_spec
from beaker.decorators import HandlerFunc, get_handler_config

# TODO make const
APP_MAX_PAGE_SIZE = 2048


class ApplicationClient:
    def __init__(
        self,
        client: AlgodClient,
        app: Application,
        app_id: int = 0,
        signer: AccountTransactionSigner = None,
        suggested_params: transaction.SuggestedParams = None,
    ):
        self.client = client
        self.app = app
        self.hints = self.app.contract_hints()

        self.signer = signer
        if self.signer is not None:
            self.addr = address_from_private_key(signer.private_key)

        self.suggested_params = suggested_params

        # Also set in create
        self.app_id = app_id

    def compile(self) -> tuple[bytes, bytes]:
        approval_result = self.client.compile(self.app.approval_program)
        approval_binary = b64decode(approval_result["result"])

        clear_result = self.client.compile(self.app.clear_program)
        clear_binary = b64decode(clear_result["result"])

        return approval_binary, clear_binary

    def create(
        self,
        signer: AccountTransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> tuple[int, str, str]:

        approval, clear = self.compile()

        extra_pages = ceil(
            ((len(approval) + len(clear)) - APP_MAX_PAGE_SIZE) / APP_MAX_PAGE_SIZE
        )

        sp = self.get_suggested_params(sp)
        signer, addr = self.get_signer(signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCreateTxn(
                    sender=addr,
                    sp=sp,
                    on_complete=transaction.OnComplete.NoOpOC,
                    approval_program=approval,
                    clear_program=clear,
                    global_schema=self.app.app_state.schema(),
                    local_schema=self.app.acct_state.schema(),
                    extra_pages=extra_pages,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        create_result = atc.execute(self.client, 4)
        create_txid = create_result.tx_ids[0]

        result = self.client.pending_transaction_info(create_txid)
        app_id = result["application-index"]
        app_addr = get_application_address(app_id)

        self.app_id = app_id

        return app_id, app_addr, create_txid

    def update(
        self,
        signer: AccountTransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        approval, clear = self.compile()

        sp = self.get_suggested_params(sp)
        signer, addr = self.get_signer(signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationUpdateTxn(
                    sender=addr,
                    sp=sp,
                    index=self.app_id,
                    approval_program=approval,
                    clear_program=clear,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        update_result = atc.execute(self.client, 4)
        return update_result.tx_ids[0]

    def delete(
        self,
        signer: AccountTransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:

        sp = self.get_suggested_params(sp)
        signer, addr = self.get_signer(signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationDeleteTxn(
                    sender=addr,
                    sp=sp,
                    index=self.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

        delete_result = atc.execute(self.client, 4)
        return delete_result.tx_ids[0]

    def prepare(
        self,
        signer: AccountTransactionSigner,
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> "ApplicationClient":
        self.signer = signer
        self.sp = sp
        self.txn_kwargs = kwargs
        return self

    def call(
        self, method: abi.Method | HandlerFunc, **kwargs
    ) -> AtomicTransactionResponse:

        sp = self.get_suggested_params()
        signer, addr = self.get_signer()

        if not isinstance(method, abi.Method):
            method = method_spec(method)

        hints = self.method_hints(method.name)

        args = []
        for method_arg in method.args:
            if method_arg.name not in kwargs or kwargs[method_arg.name] is None:
                resolvable_args = hints.get("required-args", {})
                if method_arg.name in resolvable_args:
                    result = self.call(resolvable_args[method_arg.name])
                    args.append(result.abi_results[0].return_value)
                else:
                    raise Exception(f"Unspecified argument: {method_arg.name}")
            else:
                args.append(kwargs[method_arg.name])

        if "read-only" in hints:
            read_only = hints["read-only"]
            # TODO: do dryrun

        txnkwargs = self.__dict__.get("txn_kwargs", {})

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id,
            method,
            addr,
            sp,
            signer,
            method_args=args,
            **txnkwargs,
        )

        return atc.execute(self.client, 4)

    def method_hints(self, method_name: str):
        hints = {}
        if method_name not in self.hints:
            return hints
        return self.hints[method_name]

    def get_suggested_params(
        self, sp: transaction.SuggestedParams = None
    ) -> transaction.SuggestedParams:
        if sp is not None:
            return sp

        if self.suggested_params is not None:
            return self.suggested_params

        return self.client.suggested_params()

    def get_signer(
        self, signer: AccountTransactionSigner = None
    ) -> tuple[AccountTransactionSigner, str]:
        if signer is not None:
            return (
                signer,
                address_from_private_key(signer.private_key),
            )

        if self.signer is not None:
            return (
                self.signer,
                address_from_private_key(self.signer.private_key),
            )

        raise Exception("No signer provided")
