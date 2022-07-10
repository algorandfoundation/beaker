from base64 import b64decode
from math import ceil
from typing import Any

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

from beaker.application import Application, method_spec
from beaker.decorators import HandlerFunc

# TODO make const
APP_MAX_PAGE_SIZE = 2048


class ApplicationClient:
    def __init__(self, client: AlgodClient, app: Application, app_id: int = 0):
        self.client = client
        self.app = app
        self.app_id = app_id

    def compile(self) -> tuple[bytes, bytes]:
        approval_result = self.client.compile(self.app.approval_program)
        approval_binary = b64decode(approval_result["result"])

        clear_result = self.client.compile(self.app.clear_program)
        clear_binary = b64decode(clear_result["result"])

        return approval_binary, clear_binary

    def create(
        self,
        signer: AccountTransactionSigner,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> tuple[int, str, str]:

        approval, clear = self.compile()

        extra_pages = ceil(
            ((len(approval) + len(clear)) - APP_MAX_PAGE_SIZE) / APP_MAX_PAGE_SIZE
        )

        if sp is None:
            sp = self.client.suggested_params()

        addr = address_from_private_key(signer.private_key)
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
        signer: AccountTransactionSigner,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        approval, clear = self.compile()

        if sp is None:
            sp = self.client.suggested_params()

        addr = address_from_private_key(signer.private_key)

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
        signer: AccountTransactionSigner,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:

        if sp is None:
            sp = self.client.suggested_params()

        addr = address_from_private_key(signer.private_key)

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

    def call(
        self,
        signer: AccountTransactionSigner,
        method: abi.Method | HandlerFunc,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> AtomicTransactionResponse:

        if not isinstance(method, abi.Method):
            method = method_spec(method)

        if sp is None:
            sp = self.client.suggested_params()

        addr = address_from_private_key(signer.private_key)

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id, method, addr, sp, signer, method_args=args, **kwargs
        )

        return atc.execute(self.client, 4)
