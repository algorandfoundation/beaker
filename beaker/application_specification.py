import base64
import dataclasses
import json
from pathlib import Path
from typing import Any, TypedDict, TypeAlias, Literal

from algosdk import transaction
from algosdk.abi import Contract, Method
from algosdk.abi.method import MethodDict
from algosdk.transaction import StateSchema
from pyteal import (
    Expr,
    Int,
    Bytes,
    ABIReturnSubroutine,
    CallConfig,
    MethodConfig,
    TealType,
)

from beaker.state import AccountStateValue, ApplicationStateValue, StateDict

__all__ = [
    "DefaultArgument",
    "MethodHints",
    "ApplicationSpecification",
]


class StructArgDict(TypedDict):
    name: str
    elements: list[list[str]]


DefaultArgumentClass: TypeAlias = Literal[
    "abi-method", "local-state", "global-state", "constant"
]


@dataclasses.dataclass
class DefaultArgument:
    """
    DefaultArgument is a container for any arguments that may
    be resolved prior to calling some target method
    """

    source: DefaultArgumentClass
    data: int | str | bytes | MethodDict
    stack_type: Literal["uint64", "bytes"] | None = None

    def dictify(self) -> dict[str, Any]:
        return {k: v for k, v in dataclasses.asdict(self).items() if v is not None}

    @staticmethod
    def from_resolver(
        resolver: Expr | ABIReturnSubroutine | Method | int | bytes | str,
    ) -> "DefaultArgument":
        resolvable_class: DefaultArgumentClass
        data: int | str | bytes | MethodDict
        match resolver:
            # Expr types
            case AccountStateValue() as asv:
                resolvable_class = "local-state"
                data = asv.str_key()
            case ApplicationStateValue():
                resolvable_class = "global-state"
                data = resolver.str_key()
            case Bytes():
                resolvable_class = "constant"
                data = resolver.byte_str.replace('"', "")
            case Int():
                resolvable_class = "constant"
                data = resolver.value
            # Native types
            case int() | str() | bytes():
                resolvable_class = "constant"
                data = resolver
            # FunctionType
            case Method() as method:
                resolvable_class = "abi-method"
                data = method.dictify()
            case ABIReturnSubroutine() as fn:
                if not getattr(fn, "_read_only", None):
                    raise ValueError(
                        "Only ABI methods with read_only=True should be used as default arguments to other ABI methods"
                    )
                return DefaultArgument.from_resolver(fn.method_spec())
            case _:
                raise TypeError(
                    f"Unexpected type for a default argument to ABI method: {type(resolver)}"
                )

        stack_type: Literal["uint64", "bytes"] | None
        try:
            teal_type = resolver.stack_type  # type: ignore[union-attr]
        except AttributeError:
            stack_type = None
        else:
            if teal_type == TealType.uint64:
                stack_type = "uint64"
            elif teal_type == TealType.bytes:
                stack_type = "bytes"
            else:
                stack_type = None

        return DefaultArgument(
            source=resolvable_class, data=data, stack_type=stack_type
        )


@dataclasses.dataclass
class MethodHints:
    """MethodHints provides hints to the caller about how to call the method"""

    #: hint to indicate this method can be called through Dryrun
    read_only: bool = False
    #: hint to provide names for tuple argument indices
    #: method_name=>param_name=>{name:str, elements:[str,str]}
    structs: dict[str, StructArgDict] = dataclasses.field(default_factory=dict)
    #: defaults
    default_arguments: dict[str, DefaultArgument] = dataclasses.field(
        default_factory=dict
    )
    config: MethodConfig = dataclasses.field(default_factory=MethodConfig)

    def empty(self) -> bool:
        return not self.dictify()

    def dictify(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.read_only:
            d["read_only"] = True
        if self.default_arguments:
            d["default_arguments"] = {
                k: v.dictify() for k, v in self.default_arguments.items()
            }
        if self.structs:
            d["structs"] = self.structs
        if not self.config.is_never():
            d["config"] = {
                k: v.name
                for k, v in self.config.__dict__.items()
                if v != CallConfig.NEVER
            }
        return d


@dataclasses.dataclass
class ApplicationSpecification:
    approval_program: str
    clear_program: str
    contract: Contract
    hints: dict[str, MethodHints]
    app_state: StateDict
    account_state: StateDict
    app_state_schema: StateSchema
    account_state_schema: StateSchema

    def dictify(self) -> dict:
        return {
            "hints": {k: v.dictify() for k, v in self.hints.items() if not v.empty()},
            "source": {
                "approval": base64.b64encode(self.approval_program.encode()).decode(
                    "utf8"
                ),
                "clear": base64.b64encode(self.clear_program.encode()).decode("utf8"),
            },
            "state": {
                "global": {
                    "num_byte_slices": self.app_state_schema.num_byte_slices,
                    "num_uints": self.app_state_schema.num_uints,
                },
                "local": {
                    "num_byte_slices": self.account_state_schema.num_byte_slices,
                    "num_uints": self.account_state_schema.num_uints,
                },
            },
            "schema": {
                "global": self.app_state,
                "local": self.account_state,
            },
            "contract": self.contract.dictify(),
        }

    def to_json(self) -> str:
        return json.dumps(self.dictify(), indent=4)

    @staticmethod
    def from_json(application_spec: Path | str) -> "ApplicationSpecification":
        if isinstance(application_spec, Path):
            application_spec = application_spec.read_text()

        application_json = json.loads(application_spec)
        contract = Contract.undictify(application_json["contract"])
        source = application_json["source"]
        approval_program = base64.b64decode(source["approval"]).decode("utf8")
        clear_program = base64.b64decode(source["clear"]).decode("utf8")
        schema = application_json["schema"]
        state = application_json["state"]
        local_state = transaction.StateSchema(**state["local"])
        global_state = transaction.StateSchema(**state["global"])

        hints = {
            k: _method_hints_from_json(v) for k, v in application_json["hints"].items()
        }

        return ApplicationSpecification(
            approval_program=approval_program,
            clear_program=clear_program,
            app_state=schema["global"],
            account_state=schema["local"],
            app_state_schema=global_state,
            account_state_schema=local_state,
            contract=contract,
            hints=hints,
        )

    def dump(self, directory: Path) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory: path to the directory where the artifacts should be written
        """
        directory.mkdir(exist_ok=True, parents=True)

        (directory / "approval.teal").write_text(self.approval_program)
        (directory / "clear.teal").write_text(self.clear_program)
        (directory / "contract.json").write_text(
            json.dumps(self.contract.dictify(), indent=4)
        )
        (directory / "application.json").write_text(self.to_json())


def _method_hints_from_json(method_hints: dict[str, Any]) -> MethodHints:
    method_hints["default_arguments"] = {
        k: DefaultArgument(**v)
        for k, v in method_hints.get("default_arguments", {}).items()
    }
    method_hints["config"] = MethodConfig(
        **{k: CallConfig[v] for k, v in method_hints.get("config", {}).items()}
    )
    return MethodHints(**method_hints)
