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

from .application import Application, method_spec

# TODO make const
APP_MAX_PAGE_SIZE = 2048


class ApplicationClient:
    def __init__(self, client: AlgodClient, app: Application, app_id: int = 0):
        self.client = client
        self.app = app
        self.app_id = app_id

    def create(
        self, signer: AccountTransactionSigner, args: list[Any] = [], **kwargs
    ) -> tuple[int, str, str]:
        approval_result = self.client.compile(self.app.approval_program)
        approval_compiled = b64decode(approval_result["result"])

        clear_result = self.client.compile(self.app.clear_program)
        clear_compiled = b64decode(clear_result["result"])

        extra_pages = ceil(
            ((len(approval_compiled) + len(clear_compiled)) - APP_MAX_PAGE_SIZE)
            / APP_MAX_PAGE_SIZE
        )

        sp = self.client.suggested_params()
        addr = address_from_private_key(signer.private_key)
        atc = AtomicTransactionComposer()

        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCreateTxn(
                    addr,
                    sp,
                    transaction.OnComplete.NoOpOC,
                    approval_compiled,
                    clear_compiled,
                    self.app.app_state.schema(),
                    self.app.acct_state.schema(),
                    extra_pages=extra_pages,
                    **kwargs
                ),
                signer=signer,
            )
        )
        create_result = atc.execute(self.client, 4)
        result = self.client.pending_transaction_info(create_result.tx_ids[0])
        app_id = result["application-index"]
        app_addr = get_application_address(app_id)

        self.app_id = app_id

        return app_id, app_addr, create_result.tx_ids[0]

    def update(
        self, signer: AccountTransactionSigner, args: list[Any] = [], **kwargs
    ) -> str:
        approval_result = self.client.compile(self.app.approval_program)
        approval_compiled = b64decode(approval_result["result"])

        clear_result = self.client.compile(self.app.clear_program)
        clear_compiled = b64decode(clear_result["result"])

        sp = self.client.suggested_params()
        addr = address_from_private_key(signer.private_key)

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id,
            method_spec(self.app.update),
            addr,
            sp,
            signer,
            args,
            on_complete=transaction.OnComplete.UpdateApplicationOC,
            approval_program=approval_compiled,
            clear_program=clear_compiled,
            **kwargs
        )
        update_result = atc.execute(self.client, 4)
        return update_result.tx_ids[0]

    def delete(
        self, signer: AccountTransactionSigner, args: list[Any] = [], **kwargs
    ) -> str:
        sp = self.client.suggested_params()
        addr = address_from_private_key(signer.private_key)

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id,
            method_spec(self.app.delete),
            addr,
            sp,
            signer,
            args,
            on_complete=transaction.OnComplete.DeleteApplicationOC,
            **kwargs
        )
        delete_result = atc.execute(self.client, 4)
        return delete_result.tx_ids[0]

    def call(
        self,
        signer: AccountTransactionSigner,
        method: abi.Method,
        args: list[Any] = [],
        **kwargs
    ) -> AtomicTransactionResponse:

        sp = self.client.suggested_params()
        addr = address_from_private_key(signer.private_key)

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id, method, addr, sp, signer, method_args=args, **kwargs
        )

        return atc.execute(self.client, 4)
