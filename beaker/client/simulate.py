from typing import Any
from algosdk import transaction, encoding


class PendingTransactionResponse:
    confirmed_round: int | None
    pool_error: str

    asset_index: int | None
    application_index: int | None

    #  "$ref": "#/definitions/AccountStateDelta"
    local_state_delta: list[Any]
    global_state_delta: dict[str, Any]

    inner_txns: list["PendingTransactionResponse"]
    logs: list[bytes]

    txn: transaction.SignedTransaction

    close_rewards: int | None
    close_amount: int | None
    asset_close_amount: int | None
    receiver_rewards: int | None
    sender_rewards: int | None

    @staticmethod
    def undictify(data: dict[str, Any]) -> "PendingTransactionResponse":
        ptr = PendingTransactionResponse()
        ptr.txn = encoding.msgpack_decode(data["txn"])
        ptr.logs = data.get("logs", [])
        ptr.pool_error = data.get("pool-error", "")
        ptr.confirmed_round = data.get("confirmed-round", None)
        ptr.asset_index = data.get("asset-index", None)
        ptr.application_index = data.get("application-index", None)
        ptr.local_state_delta = data.get("local-state-delta", [])
        ptr.global_state_delta = data.get("global-state-delta", {})

        if "inner_txns" in data:
            ptr.inner_txns = [
                PendingTransactionResponse.undictify(itxn)
                for itxn in data["inner_txns"]
            ]
        return ptr


class SimulationTransactionResult:
    missing_signature: bool
    result: PendingTransactionResponse

    @staticmethod
    def undictify(data: dict[str, Any]) -> "SimulationTransactionResult":
        s = SimulationTransactionResult()
        s.result = PendingTransactionResponse.undictify(data["Txn"])
        return s


class SimulationTransactionGroupResult:
    txn_results: list[SimulationTransactionResult]
    failure_message: str
    # failed_at is "transaction path": e.g. [0, 0, 1] means
    #   the second inner txn of the first inner txn of the first txn.
    failed_at: list[int]

    @staticmethod
    def undictify(data: dict[str, Any]) -> "SimulationTransactionGroupResult":
        stgr = SimulationTransactionGroupResult()
        stgr.failed_at = data.get("failedat", [])
        stgr.failure_message = data.get("failmsg", "")
        stgr.txn_results = [
            SimulationTransactionResult.undictify(t) for t in data["Txns"]
        ]
        return stgr


class SimulationResponse:
    version: int
    would_succeed: bool
    txn_groups: list[SimulationTransactionGroupResult]

    @staticmethod
    def undictify(data: dict[str, Any]) -> "SimulationResponse":
        sr = SimulationResponse()
        sr.version = data["v"]
        sr.would_succeed = data.get("s", False)
        sr.txn_groups = [
            SimulationTransactionGroupResult.undictify(txn) for txn in data["txns"]
        ]
        return sr
