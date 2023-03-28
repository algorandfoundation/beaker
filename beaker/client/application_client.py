import dataclasses
from base64 import b64decode
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from algokit_utils import ApplicationClient as AlgokitApplicationClient
from algokit_utils import (
    ApplicationSpecification,
    CommonCallParameters,
    CreateCallParameters,
    OnCompleteCallParameters,
    Program,
)
from algosdk import transaction
from algosdk.abi import Method
from algosdk.atomic_transaction_composer import (
    ABIResult,
    AtomicTransactionComposer,
    AtomicTransactionResponse,
    TransactionSigner,
    TransactionWithSigner,
)
from algosdk.transaction import SuggestedParams
from algosdk.v2client.algod import AlgodClient
from pyteal import ABIReturnSubroutine

from beaker.application import Application


class ApplicationClient:
    def __init__(
        self,
        client: AlgodClient,
        app: ApplicationSpecification | str | Path | Application,
        *,
        app_id: int = 0,
        signer: TransactionSigner | None = None,
        sender: str | None = None,
        suggested_params: SuggestedParams | None = None,
    ):
        app_spec: ApplicationSpecification
        match app:
            case ApplicationSpecification() as compiled_app:
                app_spec = compiled_app
            case Application() as app:
                app_spec = app.build(client)
            case Path() as path:
                if path.is_dir():
                    path = path / "application.json"
                app_spec = ApplicationSpecification.from_json(
                    path.read_text(encoding="utf8")
                )
            case str():
                app_spec = ApplicationSpecification.from_json(app)
            case _:
                raise Exception(f"Unexpected app type: {app}")
        self._app_client = AlgokitApplicationClient(
            client,
            app_spec,
            app_id=app_id,
            signer=signer,
            sender=sender,
            suggested_params=suggested_params,
        )

    @property
    def client(self) -> AlgodClient:
        return self._app_client.algod_client

    @property
    def app_id(self) -> int:
        return self._app_client.app_id

    @app_id.setter
    def app_id(self, value: int) -> None:
        self._app_client.app_id = value

    @property
    def app_addr(self) -> str | None:
        return self._app_client.app_address if self.app_id else None

    @property
    def sender(self) -> str | None:
        return self._app_client.sender

    @sender.setter
    def sender(self, value: str) -> None:
        self._app_client.sender = value

    @property
    def signer(self) -> TransactionSigner | None:
        return self._app_client.signer

    @signer.setter
    def signer(self, value: TransactionSigner) -> None:
        self._app_client.signer = value

    @property
    def suggested_params(self) -> transaction.SuggestedParams | None:
        return self._app_client.suggested_params

    @suggested_params.setter
    def suggested_params(self, value: transaction.SuggestedParams | None) -> None:
        self._app_client.suggested_params = value

    @property
    def approval(self) -> Program | None:
        return self._app_client.approval

    @property
    def clear(self) -> Program | None:
        return self._app_client.clear

    def get_sender(
        self, sender: str | None = None, signer: TransactionSigner | None = None
    ) -> str:
        signer, sender = self._app_client._resolve_signer_sender(signer, sender)
        return sender

    def get_signer(self, signer: TransactionSigner | None = None) -> TransactionSigner:
        signer, sender = self._app_client._resolve_signer_sender(signer, None)
        return signer

    def get_suggested_params(
        self,
        sp: transaction.SuggestedParams | None = None,
    ) -> transaction.SuggestedParams:

        if sp is not None:
            return sp

        return self._app_client.suggested_params or self.client.suggested_params()

    def add_transaction(
        self, atc: AtomicTransactionComposer, txn: transaction.Transaction
    ) -> AtomicTransactionComposer:
        if self.signer is None:
            raise Exception("No signer available")

        atc.add_transaction(TransactionWithSigner(txn=txn, signer=self.signer))
        return atc

    def create(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        extra_pages: int | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[int, str, str]:
        """Submits a signed ApplicationCallTransaction with application id == 0 and the schema and source
        from the Application passed"""
        transaction_parameters = _extract_kwargs(
            kwargs,
            sender=sender,
            signer=signer,
            suggested_params=suggested_params,
        )
        response = self._app_client.create(
            transaction_parameters=CreateCallParameters(
                extra_pages=extra_pages,
                on_complete=on_complete,
                **dataclasses.asdict(transaction_parameters),
            ),
            **kwargs,
        )
        return self._app_client.app_id, self._app_client.app_address, response.tx_id

    def update(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to UpdateApplication and source from
        the Application passed"""
        response = self._app_client.update(
            transaction_parameters=_extract_kwargs(
                kwargs,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
            ),
            **kwargs,
        )
        return response.tx_id

    def opt_in(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to OptIn"""
        response = self._app_client.opt_in(
            transaction_parameters=_extract_kwargs(
                kwargs,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
            ),
            **kwargs,
        )
        return response.tx_id

    def close_out(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to CloseOut"""
        response = self._app_client.close_out(
            transaction_parameters=_extract_kwargs(
                kwargs,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
            ),
            **kwargs,
        )
        return response.tx_id

    def clear_state(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to ClearState"""
        response = self._app_client.clear_state(
            transaction_parameters=_extract_kwargs(
                kwargs,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
            ),
            app_args=kwargs.pop("app_args", None),
        )
        return response.tx_id

    def delete(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to DeleteApplication"""
        response = self._app_client.delete(
            transaction_parameters=_extract_kwargs(
                kwargs,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
            ),
            **kwargs,
        )
        return response.tx_id

    def add_method_call(
        self,
        atc: AtomicTransactionComposer,
        method: Method | ABIReturnSubroutine | str,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        local_schema: transaction.StateSchema | None = None,
        global_schema: transaction.StateSchema | None = None,
        approval_program: bytes | None = None,
        clear_program: bytes | None = None,
        extra_pages: int | None = None,
        accounts: list[str] | None = None,
        foreign_apps: list[int] | None = None,
        foreign_assets: list[int] | None = None,
        boxes: Sequence[tuple[int, bytes | bytearray | str | int]] | None = None,
        note: bytes | None = None,
        lease: bytes | None = None,
        rekey_to: str | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> AtomicTransactionComposer:
        self._app_client.add_method_call(
            atc,
            method,
            abi_args=kwargs,
            parameters=CommonCallParameters(
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
                note=note,
                lease=lease,
                accounts=accounts,
                foreign_apps=foreign_apps,
                foreign_assets=foreign_assets,
                boxes=boxes,
                rekey_to=rekey_to,
            ),
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            extra_pages=extra_pages,
        )
        return atc

    def call(
        self,
        method: Method | ABIReturnSubroutine | str,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        accounts: list[str] | None = None,
        foreign_apps: list[int] | None = None,
        foreign_assets: list[int] | None = None,
        boxes: Sequence[tuple[int, bytes | bytearray | str | int]] | None = None,
        note: bytes | None = None,
        lease: bytes | None = None,
        rekey_to: str | None = None,
        atc: AtomicTransactionComposer | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> ABIResult:
        if not atc:
            atc = AtomicTransactionComposer()
        deprecated_arguments = [
            kwargs.pop("local_schema", None),
            kwargs.pop("global_schema", None),
            kwargs.pop("approval_program", None),
            kwargs.pop("clear_program", None),
            kwargs.pop("extra_pages", None),
        ]
        if any(deprecated_arguments):
            raise Exception(
                "Can't create an application using call, either create an application from "
                "the client app_spec using create() or use add_method_call() instead."
            )
        self._app_client.compose_call(
            atc,
            call_abi_method=method,
            transaction_parameters=OnCompleteCallParameters(
                on_complete=on_complete,
                sender=sender,
                signer=signer,
                suggested_params=suggested_params,
                note=note,
                lease=lease,
                accounts=accounts,
                foreign_apps=foreign_apps,
                foreign_assets=foreign_assets,
                boxes=boxes,
                rekey_to=rekey_to,
            ),
            **kwargs,
        )
        result = self.execute_atc(atc)
        return result.abi_results[0]

    def execute_atc(self, atc: AtomicTransactionComposer) -> AtomicTransactionResponse:
        return self._app_client.execute_atc(atc)

    def fund(self, amt: int, addr: str | None = None) -> str:
        """convenience method to pay the address passed, defaults to paying the app address for
        this client from the current signer"""
        sender = self.get_sender()
        signer = self.get_signer()

        sp = self.client.suggested_params()

        rcv = self.app_addr if addr is None else addr

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.PaymentTxn(sender, sp, rcv, amt),
                signer=signer,
            )
        )
        atc.execute(self.client, 4)
        return atc.tx_ids.pop()

    def get_application_account_info(self) -> dict[str, Any]:
        """gets the account info for the application account"""
        assert self.app_addr
        info = self.client.account_info(self.app_addr)
        assert isinstance(info, dict)
        return info

    def get_box_names(self) -> list[bytes]:
        box_resp = self.client.application_boxes(self.app_id)
        assert isinstance(box_resp, dict)
        return [b64decode(box["name"]) for box in box_resp["boxes"]]

    def get_box_contents(self, name: bytes) -> bytes:
        contents = self.client.application_box_by_name(self.app_id, name)
        assert isinstance(contents, dict)
        return b64decode(contents["value"])

    def get_local_state(
        self, account: str | None = None, *, raw: bool = False
    ) -> dict[bytes | str, bytes | str | int]:
        return self._app_client.get_local_state(account, raw=raw)

    def get_global_state(
        self, *, raw: bool = False
    ) -> dict[bytes | str, bytes | str | int]:
        return self._app_client.get_global_state(raw=raw)

    def prepare(
        self,
        signer: TransactionSigner | None = None,
        sender: str | None = None,
        app_id: int | None = None,
    ) -> "ApplicationClient":
        """makes a copy of the current ApplicationClient and the fields passed"""
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)
        copy = ApplicationClient(
            self.client,
            self._app_client.app_spec,
            app_id=self.app_id if app_id is None else app_id,
            signer=signer,
            sender=sender,
            suggested_params=self.suggested_params,
        )
        copy._app_client = copy._app_client.prepare(
            signer=signer, sender=sender, app_id=app_id
        )
        return copy


def _extract_kwargs(
    kwargs: dict[str, Any],
    sender: str | None,
    signer: TransactionSigner | None,
    suggested_params: transaction.SuggestedParams | None,
) -> CommonCallParameters:
    return CommonCallParameters(
        sender=sender,
        signer=signer,
        suggested_params=suggested_params,
        note=kwargs.pop("note", None),
        lease=kwargs.pop("lease", None),
        accounts=kwargs.pop("accounts", None),
        foreign_apps=kwargs.pop("foreign_apps", None),
        foreign_assets=kwargs.pop("foreign_assets", None),
        boxes=kwargs.pop("boxes", None),
        rekey_to=kwargs.pop("rekey_to", None),
    )
