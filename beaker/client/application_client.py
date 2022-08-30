from base64 import b64decode
import copy
from math import ceil
from typing import Any, cast

from algosdk.account import address_from_private_key
from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AccountTransactionSigner,
    MultisigTransactionSigner,
    LogicSigTransactionSigner,
    AtomicTransactionComposer,
    ABIResult,
    ABI_RETURN_HASH,
    TransactionWithSigner,
    abi,
)
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk.source_map import SourceMap
from algosdk.v2client.algod import AlgodClient
from algosdk.constants import APP_PAGE_MAX_SIZE

from beaker.application import Application, get_method_spec
from beaker.decorators import (
    HandlerFunc,
    MethodHints,
    DefaultArgument,
    DefaultArgumentClass,
)
from beaker.client.state_decode import decode_state
from beaker.client.logic_error import LogicException


class ApplicationClient:
    def __init__(
        self,
        client: AlgodClient,
        app: Application,
        app_id: int = 0,
        signer: TransactionSigner = None,
        sender: str = None,
        suggested_params: transaction.SuggestedParams = None,
    ):
        self.client = client
        self.app = app
        self.app_id = app_id
        self.app_addr = get_application_address(app_id) if self.app_id != 0 else None

        self.signer = signer
        self.sender = sender
        if signer is not None and sender is None:
            self.sender = self.get_sender(sender, self.signer)

        self.approval_binary = None
        self.approval_src_map = None

        self.clear_binary = None
        self.clear_src_map = None

        self.suggested_params = suggested_params

    def compile(
        self, teal: str, source_map: bool = False
    ) -> tuple[bytes, str, SourceMap]:
        result = self.client.compile(teal, source_map=source_map)
        src_map = None
        if source_map:
            src_map = SourceMap(result["sourcemap"])
        return (b64decode(result["result"]), result["hash"], src_map)

    def build(self):
        recompile = False
        for _, v in self.app.precompiles.items():
            if v.binary is None:
                binary, addr, map = self.compile(v.program, True)
                v._set_compiled(binary, addr, map)
                recompile = True

        if recompile:
            self.app.compile()

        if self.approval_binary is None or recompile:
            approval, _, approval_map = self.compile(self.app.approval_program, True)
            self.approval_binary = approval
            self.approval_src_map = approval_map

        if self.clear_binary is None or recompile:
            clear, _, clear_map = self.compile(self.app.clear_program, True)
            self.clear_binary = clear
            self.clear_src_map = clear_map

    def create(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        extra_pages: int = None,
        **kwargs,
    ) -> tuple[int, str, str]:
        """Submits a signed ApplicationCallTransaction with application id == 0 and the schema and source from the Application passed"""

        self.build()
        assert self.clear_binary is not None and self.approval_binary is not None

        if extra_pages is None:
            extra_pages = ceil(
                (
                    (len(self.approval_binary) + len(self.clear_binary))
                    - APP_PAGE_MAX_SIZE
                )
                / APP_PAGE_MAX_SIZE
            )

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_create is not None:
            self.add_method_call(
                atc,
                self.app.on_create,
                sender=sender,
                sp=sp,
                on_complete=on_complete,
                approval_program=self.approval_binary,
                clear_program=self.clear_binary,
                global_schema=self.app.app_state.schema(),
                local_schema=self.app.acct_state.schema(),
                extra_pages=extra_pages,
                app_args=args,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationCreateTxn(
                        sender=sender,
                        sp=sp,
                        on_complete=on_complete,
                        approval_program=self.approval_binary,
                        clear_program=self.clear_binary,
                        global_schema=self.app.app_state.schema(),
                        local_schema=self.app.acct_state.schema(),
                        extra_pages=extra_pages,
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        try:
            create_result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

        create_txid = create_result.tx_ids[0]

        result = self.client.pending_transaction_info(create_txid)
        app_id = result["application-index"]
        app_addr = get_application_address(app_id)

        self.app_id = app_id
        self.app_addr = app_addr

        return app_id, app_addr, create_txid

    def update(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:

        """Submits a signed ApplicationCallTransaction with OnComplete set to UpdateApplication and source from the Application passed"""
        self.build()

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_update is not None:
            self.add_method_call(
                atc,
                self.app.on_update,
                on_complete=transaction.OnComplete.UpdateApplicationOC,
                sender=sender,
                sp=sp,
                index=self.app_id,
                approval_program=self.approval_binary,
                clear_program=self.clear_binary,
                app_args=args,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationUpdateTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        approval_program=self.approval_binary,
                        clear_program=self.clear_binary,
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        try:
            update_result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

        return update_result.tx_ids[0]

    def opt_in(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to OptIn"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_opt_in is not None:
            self.add_method_call(
                atc,
                self.app.on_opt_in,
                on_complete=transaction.OnComplete.OptInOC,
                sender=sender,
                sp=sp,
                index=self.app_id,
                app_args=args,
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
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        try:
            opt_in_result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

        return opt_in_result.tx_ids[0]

    def close_out(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to CloseOut"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_close_out is not None:
            self.add_method_call(
                atc,
                self.app.on_close_out,
                on_complete=transaction.OnComplete.CloseOutOC,
                sender=sender,
                sp=sp,
                index=self.app_id,
                app_args=args,
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
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        try:
            close_out_result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

        return close_out_result.tx_ids[0]

    def clear_state(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:

        """Submits a signed ApplicationCallTransaction with OnComplete set to ClearState"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_clear_state is not None:
            self.add_method_call(
                atc,
                self.app.on_clear_state,
                on_complete=transaction.OnComplete.ClearStateOC,
                sender=sender,
                sp=sp,
                index=self.app_id,
                app_args=args,
                signer=signer,
                **kwargs,
            )
        else:
            atc.add_transaction(
                TransactionWithSigner(
                    txn=transaction.ApplicationClearStateTxn(
                        sender=sender,
                        sp=sp,
                        index=self.app_id,
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        clear_state_result = atc.execute(self.client, 4)

        return clear_state_result.tx_ids[0]

    def delete(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = None,
        suggested_params: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        """Submits a signed ApplicationCallTransaction with OnComplete set to DeleteApplication"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        if self.app.on_delete:
            self.add_method_call(
                atc,
                self.app.on_delete,
                sender=sender,
                sp=sp,
                index=self.app_id,
                app_args=args,
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
                        app_args=args,
                        **kwargs,
                    ),
                    signer=signer,
                )
            )

        try:
            delete_result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

        return delete_result.tx_ids[0]

    def prepare(
        self, signer: TransactionSigner = None, sender: str = None, **kwargs
    ) -> "ApplicationClient":

        """makes a copy of the current ApplicationClient and the fields passed"""

        ac = copy.copy(self)
        ac.signer = ac.get_signer(signer)
        ac.sender = ac.get_sender(sender, ac.signer)
        ac.__dict__.update(**kwargs)
        return ac

    def call(
        self,
        method: abi.Method | HandlerFunc,
        sender: str = None,
        signer: TransactionSigner = None,
        suggested_params: transaction.SuggestedParams = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        local_schema: transaction.StateSchema = None,
        global_schema: transaction.StateSchema = None,
        approval_program: bytes = None,
        clear_program: bytes = None,
        extra_pages: int = None,
        accounts: list[str] = None,
        foreign_apps: list[int] = None,
        foreign_assets: list[int] = None,
        note: bytes = None,
        lease: bytes = None,
        rekey_to: str = None,
        **kwargs,
    ) -> ABIResult:

        """Handles calling the application"""

        if not isinstance(method, abi.Method):
            method = get_method_spec(method)

        hints = self.method_hints(method.name)

        atc = self.add_method_call(
            AtomicTransactionComposer(),
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
            **kwargs,
        )

        # If its a read-only method, use dryrun (TODO: swap with simulate later?)
        if hints.read_only:
            dr_req = transaction.create_dryrun(self.client, atc.gather_signatures())
            dr_result = self.client.dryrun(dr_req)
            method_results = self._parse_result(
                {0: method}, dr_result["txns"], atc.tx_ids
            )
            return method_results.pop()

        try:
            result = atc.execute(self.client, 4)
        except Exception as e:
            if "logic" in str(e):
                raise self.wrap_approval_exception(e)
            else:
                raise e

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

            raw_value = None
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
                return_value = methods[i].returns.type.decode(raw_value)
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
        method: abi.Method | HandlerFunc,
        sender: str = None,
        signer: TransactionSigner = None,
        suggested_params: transaction.SuggestedParams = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        local_schema: transaction.StateSchema = None,
        global_schema: transaction.StateSchema = None,
        approval_program: bytes = None,
        clear_program: bytes = None,
        extra_pages: int = None,
        accounts: list[str] = None,
        foreign_apps: list[int] = None,
        foreign_assets: list[int] = None,
        note: bytes = None,
        lease: bytes = None,
        rekey_to: str = None,
        **kwargs,
    ):

        """Adds a transaction to the AtomicTransactionComposer passed"""

        sp = self.get_suggested_params(suggested_params)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        if not isinstance(method, abi.Method):
            method = get_method_spec(method)

        hints = self.method_hints(method.name)

        args = []
        for method_arg in method.args:
            name = method_arg.name

            if name in kwargs:
                argument = kwargs[name]

                if type(argument) is dict:
                    if hints.structs is None or name not in hints.structs:
                        raise Exception(f"Name {name} name in struct hints")

                    elems: list[tuple[str, str]] = cast(
                        list[tuple[str, str]], hints.structs[name]["elements"]
                    )

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
            note=note,
            lease=lease,
            rekey_to=rekey_to,
        )

        return atc

    def add_transaction(
        self, atc: AtomicTransactionComposer, txn: transaction.Transaction
    ) -> AtomicTransactionComposer:
        atc.add_transaction(TransactionWithSigner(txn=txn, signer=self.signer))
        return atc

    def fund(self, amt: int) -> str:
        """fund pays the app account the amount passed using the signer"""
        sender = self.get_sender()
        signer = self.get_signer()

        sp = self.client.suggested_params()

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.PaymentTxn(sender, sp, self.app_addr, amt),
                signer=signer,
            )
        )
        atc.execute(self.client, 4)
        return atc.tx_ids.pop()

    def get_application_state(self, raw=False) -> dict[bytes | str, bytes | str | int]:
        """gets the global state info for the app id set"""
        app_state = self.client.application_info(self.app_id)
        if "params" not in app_state or "global-state" not in app_state["params"]:
            return {}
        return decode_state(app_state["params"]["global-state"], raw=raw)

    def get_account_state(
        self, account: str = None, raw: bool = False
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

        return decode_state(acct_state["app-local-state"]["key-value"], raw=raw)

    def get_application_account_info(self) -> dict[str, Any]:
        """gets the account info for the application account"""
        app_state = self.client.account_info(self.app_addr)
        return app_state

    def resolve(self, to_resolve: DefaultArgument) -> Any:
        if to_resolve.resolvable_class == DefaultArgumentClass.Constant:
            return to_resolve.resolve_hint()
        elif to_resolve.resolvable_class == DefaultArgumentClass.GlobalState:
            key = to_resolve.resolve_hint()
            app_state = self.get_application_state()
            return app_state[key]
        elif to_resolve.resolvable_class == DefaultArgumentClass.LocalState:
            key = to_resolve.resolve_hint()
            acct_state = self.get_account_state(
                self.get_sender(),
            )
            return acct_state[key]
        elif to_resolve.resolvable_class == DefaultArgumentClass.ABIMethod:
            method = abi.Method.undictify(to_resolve.resolve_hint())
            result = self.call(method)
            return result.return_value
        else:
            raise Exception(f"Unrecognized resolver: {to_resolve}")

    def method_hints(self, method_name: str) -> MethodHints:
        if method_name not in self.app.hints:
            return MethodHints()
        return self.app.hints[method_name]

    def get_suggested_params(
        self, sp: transaction.SuggestedParams = None
    ) -> transaction.SuggestedParams:

        if sp is not None:
            return sp

        if self.suggested_params is not None:
            return self.suggested_params

        return self.client.suggested_params()

    def wrap_approval_exception(self, e: Exception) -> Exception:
        if self.approval_src_map is None:
            if self.app.approval_program is None:
                return e

            _, _, map = self.compile(self.app.approval_program, True)
            self.approval_src_map = map

        return LogicException(e, self.app.approval_program, self.approval_src_map)

    def get_signer(self, signer: TransactionSigner = None) -> TransactionSigner:
        if signer is not None:
            return signer

        if self.signer is not None:
            return self.signer

        raise Exception("No signer provided")

    def get_sender(self, sender: str = None, signer: TransactionSigner = None) -> str:
        if sender is not None:
            return sender

        if signer is None and self.sender is not None:
            return self.sender

        signer = self.get_signer(signer)

        match signer:
            case AccountTransactionSigner():  # type: ignore
                return address_from_private_key(signer.private_key)
            case MultisigTransactionSigner():  # type: ignore
                return signer.msig.address()
            case LogicSigTransactionSigner():  # type: ignore
                return signer.lsig.address()

        raise Exception("No sender provided")
