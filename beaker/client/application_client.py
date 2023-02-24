import copy
import dataclasses
import warnings
from base64 import b64decode
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import algosdk
from algosdk import abi, transaction
from algosdk.account import address_from_private_key
from algosdk.atomic_transaction_composer import (
    ABI_RETURN_HASH,
    ABIResult,
    AccountTransactionSigner,
    AtomicTransactionComposer,
    AtomicTransactionResponse,
    LogicSigTransactionSigner,
    MultisigTransactionSigner,
    TransactionSigner,
    TransactionWithSigner,
)
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient
from pyteal import ABIReturnSubroutine, CallConfig, MethodConfig

from beaker.application import Application
from beaker.application_specification import (
    ApplicationSpecification,
    DefaultArgumentDict,
    MethodHints,
)
from beaker.client.logic_error import LogicException, parse_logic_error
from beaker.client.state_decode import decode_state
from beaker.compilation import Program
from beaker.consts import num_extra_program_pages


class ApplicationClient:
    def __init__(
        self,
        client: AlgodClient,
        app: ApplicationSpecification | str | Path | Application,
        app_id: int = 0,
        signer: TransactionSigner | None = None,
        sender: str | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
    ):
        self.client = client
        self.app: ApplicationSpecification
        match app:
            case ApplicationSpecification() as compiled_app:
                self.app = compiled_app
            case Application() as app:
                self.app = app.build(client)
            case Path() as path:
                if path.is_dir():
                    path = path / "application.json"
                self.app = ApplicationSpecification.from_json(
                    path.read_text(encoding="utf8")
                )
            case str():
                self.app = ApplicationSpecification.from_json(app)
        self.app_id = app_id
        self.app_addr = get_application_address(app_id) if self.app_id != 0 else None

        self.signer = signer
        self.sender = sender
        if signer is not None and sender is None:
            self.sender = self.get_sender(sender, self.signer)

        self.approval = Program(self.app.approval_program, self.client)
        self.clear = Program(self.app.clear_program, self.client)

        self.suggested_params = suggested_params

        def find_method(predicate: Callable[[MethodConfig], bool]) -> abi.Method | None:
            matching = [
                method
                for method in self.app.contract.methods
                if predicate(self._method_hints(method).call_config)
            ]
            if len(matching) == 1:
                return matching[0]
            elif len(matching) > 1:
                # TODO: warn?
                pass
            return None

        self.on_create = find_method(
            lambda x: any([x & CallConfig.CREATE for x in dataclasses.astuple(x)])
        )
        self.on_update = find_method(lambda x: x.update_application != CallConfig.NEVER)
        self.on_opt_in = find_method(lambda x: x.opt_in != CallConfig.NEVER)
        self.on_close_out = find_method(lambda x: x.close_out != CallConfig.NEVER)
        self.on_delete = find_method(lambda x: x.delete_application != CallConfig.NEVER)

    def create(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        extra_pages: int | None = None,
        **kwargs: Any,
    ) -> tuple[int, str, str]:
        """Submits a signed ApplicationCallTransaction with application id == 0 and the schema and source from the Application passed"""

        if extra_pages is None:
            extra_pages = num_extra_program_pages(
                self.approval.raw_binary, self.clear.raw_binary
            )

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.on_create is not None:
            self.add_method_call(
                atc,
                self.on_create,
                sender=sender,
                suggested_params=sp,
                on_complete=on_complete,
                approval_program=self.approval.raw_binary,
                clear_program=self.clear.raw_binary,
                global_schema=self.app.global_state_schema,
                local_schema=self.app.local_state_schema,
                extra_pages=extra_pages,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationCreateTxn(
                        sender=sender,
                        sp=sp,
                        on_complete=on_complete,
                        approval_program=self.approval.raw_binary,
                        clear_program=self.clear.raw_binary,
                        global_schema=self.app.global_state_schema,
                        local_schema=self.app.local_state_schema,
                        extra_pages=extra_pages,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        create_result = self._execute_atc(atc)

        create_txid = create_result.tx_ids[0]

        result = self.client.pending_transaction_info(create_txid)
        app_id = result["application-index"]
        app_addr = get_application_address(app_id)

        self.app_id = app_id
        self.app_addr = app_addr

        return app_id, app_addr, create_txid

    def update(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to UpdateApplication and source from the Application passed"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.on_update is not None:
            self.add_method_call(
                atc,
                self.on_update,
                on_complete=transaction.OnComplete.UpdateApplicationOC,
                sender=sender,
                suggested_params=sp,
                approval_program=self.approval.raw_binary,
                clear_program=self.clear.raw_binary,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationUpdateTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        approval_program=self.approval.raw_binary,
                        clear_program=self.clear.raw_binary,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        update_result = self._execute_atc(atc)

        return update_result.tx_ids[0]

    def opt_in(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to OptIn"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.on_opt_in is not None:
            self.add_method_call(
                atc,
                self.on_opt_in,
                on_complete=transaction.OnComplete.OptInOC,
                sender=sender,
                suggested_params=sp,
                signer=signer,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationOptInTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        opt_in_result = self._execute_atc(atc)

        return opt_in_result.tx_ids[0]

    def close_out(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to CloseOut"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.on_close_out is not None:
            self.add_method_call(
                atc,
                self.on_close_out,
                on_complete=transaction.OnComplete.CloseOutOC,
                sender=sender,
                suggested_params=sp,
                signer=signer,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationCloseOutTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        close_out_result = self._execute_atc(atc)

        return close_out_result.tx_ids[0]

    def clear_state(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to ClearState"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationClearStateTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    **kwargs,
                ),
                signer=signer,
            )
        )

        clear_state_result = atc.execute(self.client, 4)

        return clear_state_result.tx_ids[0]

    def delete(
        self,
        sender: str | None = None,
        signer: TransactionSigner | None = None,
        suggested_params: transaction.SuggestedParams | None = None,
        **kwargs: Any,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to DeleteApplication"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.on_delete:
            self.add_method_call(
                atc,
                self.on_delete,
                on_complete=transaction.OnComplete.DeleteApplicationOC,
                sender=sender,
                suggested_params=sp,
                signer=signer,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationDeleteTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        delete_result = self._execute_atc(atc)

        return delete_result.tx_ids[0]

    def prepare(
        self,
        signer: TransactionSigner | None = None,
        sender: str | None = None,
        **kwargs: Any,
    ) -> "ApplicationClient":

        """makes a copy of the current ApplicationClient and the fields passed"""

        ac = copy.copy(self)
        ac.signer = ac.get_signer(signer)
        ac.sender = ac.get_sender(sender, ac.signer)
        ac.__dict__.update(**kwargs)
        return ac

    def call(
        self,
        method: abi.Method | ABIReturnSubroutine | str,
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
        atc: AtomicTransactionComposer | None = None,
        **kwargs: Any,
    ) -> ABIResult:

        """Handles calling the application"""

        method = self._resolve_abi_method(method)
        hints = self._method_hints(method)

        if atc is None:
            atc = AtomicTransactionComposer()

        atc = self.add_method_call(
            atc,
            method,
            sender,
            signer,
            suggested_params=suggested_params,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            extra_pages=extra_pages,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
            boxes=boxes,
            **kwargs,
        )
        if atc is None:
            raise Exception("ATC none?")

        # If its a read-only method, use dryrun (TODO: swap with simulate later?)
        if hints.read_only:
            dr_req = transaction.create_dryrun(self.client, atc.gather_signatures())
            dr_result = self.client.dryrun(dr_req)
            for txn in dr_result["txns"]:
                if "app-call-messages" in txn:
                    if "REJECT" in txn["app-call-messages"]:
                        msg = ", ".join(txn["app-call-messages"])
                        raise Exception(f"Dryrun for readonly method failed: {msg}")

            method_results = self._parse_result(
                {0: method}, dr_result["txns"], atc.tx_ids
            )
            return method_results.pop()

        result = self._execute_atc(atc)

        return result.abi_results.pop()

    # TEMPORARY, use SDK one when available
    def _parse_result(
        self,
        methods: dict[int, abi.Method],
        txns: list[dict[str, Any]],
        txids: list[str],
    ) -> list[ABIResult]:
        method_results = []
        for i, tx_info in enumerate(txns):

            raw_value = b""
            return_value = None
            decode_error = None

            if i not in methods:
                continue

            # Parse log for ABI method return value
            try:
                if methods[i].returns.type == abi.Returns.VOID:
                    method_results.append(
                        ABIResult(
                            tx_id=txids[i],
                            raw_value=raw_value,
                            return_value=return_value,
                            decode_error=decode_error,
                            tx_info=tx_info,
                            method=methods[i],
                        )
                    )
                    continue

                logs = tx_info["logs"] if "logs" in tx_info else []

                # Look for the last returned value in the log
                if not logs:
                    raise Exception("No logs")

                result = logs[-1]
                # Check that the first four bytes is the hash of "return"
                result_bytes = b64decode(result)
                if len(result_bytes) < 4 or result_bytes[:4] != ABI_RETURN_HASH:
                    raise Exception("no logs")

                raw_value = result_bytes[4:]
                abi_return_type = methods[i].returns.type
                if isinstance(abi_return_type, abi.ABIType):
                    return_value = abi_return_type.decode(raw_value)
                else:
                    return_value = raw_value

            except Exception as e:
                decode_error = e

            method_results.append(
                ABIResult(
                    tx_id=txids[i],
                    raw_value=raw_value,
                    return_value=return_value,
                    decode_error=decode_error,
                    tx_info=tx_info,
                    method=methods[i],
                )
            )

        return method_results

    def add_method_call(
        self,
        atc: AtomicTransactionComposer,
        method: abi.Method | ABIReturnSubroutine | str,
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
        **kwargs: Any,
    ) -> AtomicTransactionComposer:

        """Adds a transaction to the AtomicTransactionComposer passed"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        method = self._resolve_abi_method(method)
        hints = self._method_hints(method)

        args = []
        for method_arg in method.args:
            name = method_arg.name
            if name in kwargs:
                argument = kwargs.pop(name)
                if isinstance(argument, dict):
                    if hints.structs is None or name not in hints.structs:
                        raise Exception(
                            f"Argument missing struct hint: {name}. Check argument name and type"
                        )

                    elems = hints.structs[name]["elements"]

                    argument = [
                        argument[field_name] for field_name, field_type in elems
                    ]

                args.append(argument)

            elif (
                hints.default_arguments is not None and name in hints.default_arguments
            ):
                default_arg = hints.default_arguments[name]
                if default_arg is not None:
                    args.append(self.resolve(default_arg))
            else:
                raise Exception(f"Unspecified argument: {name}")
        if kwargs:
            warnings.warn(f"Unused arguments specified: {', '.join(kwargs)}")
        if boxes is not None:
            # TODO: algosdk actually does this, but it's type hints say otherwise...
            encoded_boxes = [
                (id_, algosdk.encoding.encode_as_bytes(name)) for id_, name in boxes
            ]
        else:
            encoded_boxes = None
        atc.add_method_call(
            self.app_id,
            method,
            sender,
            sp,
            signer,
            method_args=args,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            extra_pages=extra_pages,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            boxes=encoded_boxes,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
        )

        return atc

    def _resolve_abi_method(
        self, method: abi.Method | ABIReturnSubroutine | str
    ) -> abi.Method:
        if isinstance(method, ABIReturnSubroutine):
            return method.method_spec()
        elif isinstance(method, str):
            try:
                return next(
                    iter(
                        m
                        for m in self.app.contract.methods
                        if m.get_signature() == method
                    )
                )
            except StopIteration:
                pass
            return self.app.contract.get_method_by_name(method)
        else:
            return method

    def add_transaction(
        self, atc: AtomicTransactionComposer, txn: transaction.Transaction
    ) -> AtomicTransactionComposer:
        if self.signer is None:
            raise Exception("No signer available")

        atc.add_transaction(TransactionWithSigner(txn=txn, signer=self.signer))
        return atc

    def fund(self, amt: int, addr: str | None = None) -> str:
        """convenience method to pay the address passed, defaults to paying the app address for this client from the current signer"""
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

    def get_global_state(
        self, raw: bool = False
    ) -> dict[bytes | str, bytes | str | int]:
        """gets the global state info for the app id set"""
        global_state = self.client.application_info(self.app_id)
        return cast(
            dict[bytes | str, bytes | str | int],
            decode_state(
                global_state.get("params", {}).get("global-state", {}), raw=raw
            ),
        )

    def get_local_state(
        self, account: str | None = None, raw: bool = False
    ) -> dict[str | bytes, bytes | str | int]:

        """gets the local state info for the app id set and the account specified"""

        if account is None:
            account = self.get_sender()

        acct_state = self.client.account_application_info(account, self.app_id)
        if (
            "app-local-state" not in acct_state
            or "key-value" not in acct_state["app-local-state"]
        ):
            return {}

        return cast(
            dict[str | bytes, bytes | str | int],
            decode_state(acct_state["app-local-state"]["key-value"], raw=raw),
        )

    def get_application_account_info(self) -> dict[str, Any]:
        """gets the account info for the application account"""
        return self.client.account_info(self.app_addr)

    def get_box_names(self) -> list[bytes]:
        box_resp = self.client.application_boxes(self.app_id)
        return [b64decode(box["name"]) for box in box_resp["boxes"]]

    def get_box_contents(self, name: bytes) -> bytes:
        contents = self.client.application_box_by_name(self.app_id, name)
        return b64decode(contents["value"])

    def resolve(self, to_resolve: DefaultArgumentDict) -> Any:  # noqa: ANN401
        match to_resolve:
            case {"source": "constant", "data": data}:
                return data
            case {"source": "global-state", "data": str() as key}:
                global_state = self.get_global_state(raw=True)
                return global_state[key.encode()]
            case {"source": "local-state", "data": str() as key}:
                acct_state = self.get_local_state(self.get_sender(), raw=True)
                return acct_state[key.encode()]
            case {"source": "abi-method", "data": dict() as method_dict}:
                method = abi.Method.undictify(method_dict)
                result = self.call(method)
                return result.return_value
            case {"source": source}:
                raise ValueError(f"Unrecognized default argument source: {source}")
            case _:
                raise TypeError("Unable to interpret default argument specification")

    def _method_hints(self, method: abi.Method) -> MethodHints:
        sig = method.get_signature()
        if sig not in self.app.hints:
            return MethodHints()
        return self.app.hints[sig]

    def get_suggested_params(
        self,
        sp: transaction.SuggestedParams | None = None,
    ) -> transaction.SuggestedParams:

        if sp is not None:
            return sp

        if self.suggested_params is not None:
            return self.suggested_params

        return self.client.suggested_params()

    def _execute_atc(
        self, atc: AtomicTransactionComposer, wait_rounds: int = 4
    ) -> AtomicTransactionResponse:
        try:
            return atc.execute(self.client, wait_rounds=wait_rounds)
        except Exception as ex:
            if self.approval.source_map and self.approval.raw_binary:
                logic_error_data = parse_logic_error(str(ex))
                if logic_error_data is not None:
                    raise LogicException(
                        logic_error=ex,
                        program=self.approval.teal,
                        map=self.approval.source_map,
                        **logic_error_data,
                    ) from ex
            raise ex

    def get_signer(self, signer: TransactionSigner | None = None) -> TransactionSigner:
        if signer is not None:
            return signer

        if self.signer is not None:
            return self.signer

        raise Exception("No signer provided")

    def get_sender(
        self, sender: str | None = None, signer: TransactionSigner | None = None
    ) -> str:
        if sender is not None:
            return sender

        if signer is None and self.sender is not None:
            return self.sender

        signer = self.get_signer(signer)

        if isinstance(signer, AccountTransactionSigner):
            return address_from_private_key(signer.private_key)
        elif isinstance(signer, MultisigTransactionSigner):
            return signer.msig.address()
        elif isinstance(signer, LogicSigTransactionSigner):
            return signer.lsig.address()

        raise Exception("No sender provided")
