import base64
import dataclasses
import json
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypedDict

from algosdk.abi import Contract
from algosdk.abi.method import MethodDict
from algosdk.transaction import StateSchema
from pyteal import CallConfig, MethodConfig, PyTealSourceMap

__all__ = [
    "DefaultArgumentDict",
    "DefaultArgumentType",
    "MethodHints",
    "ApplicationSpecification",
    "AppSpecStateDict",
]

AppSpecStateDict: TypeAlias = dict[str, dict[str, dict]]


class StructArgDict(TypedDict):
    name: str
    elements: list[list[str]]


DefaultArgumentType: TypeAlias = Literal[
    "abi-method", "local-state", "global-state", "constant"
]


class DefaultArgumentDict(TypedDict):
    """
    DefaultArgument is a container for any arguments that may
    be resolved prior to calling some target method
    """

    source: DefaultArgumentType
    data: int | str | bytes | MethodDict


StateDict = TypedDict(  # noqa: UP013  # can't convert as "global" is a reserved keyword
    "StateDict", {"global": AppSpecStateDict, "local": AppSpecStateDict}
)


@dataclasses.dataclass(kw_only=True)
class MethodHints:
    """MethodHints provides hints to the caller about how to call the method"""

    #: hint to indicate this method can be called through Dryrun
    read_only: bool = False
    #: hint to provide names for tuple argument indices
    #: method_name=>param_name=>{name:str, elements:[str,str]}
    structs: dict[str, StructArgDict] = dataclasses.field(default_factory=dict)
    #: defaults
    default_arguments: dict[str, DefaultArgumentDict] = dataclasses.field(
        default_factory=dict
    )
    call_config: MethodConfig = dataclasses.field(default_factory=MethodConfig)

    def empty(self) -> bool:
        return not self.dictify()

    def dictify(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.read_only:
            d["read_only"] = True
        if self.default_arguments:
            d["default_arguments"] = self.default_arguments
        if self.structs:
            d["structs"] = self.structs
        if not self.call_config.is_never():
            d["call_config"] = _encode_method_config(self.call_config)
        return d

    @staticmethod
    def undictify(data: dict[str, Any]) -> "MethodHints":
        return MethodHints(
            read_only=data.get("read_only", False),
            default_arguments=data.get("default_arguments", {}),
            structs=data.get("structs", {}),
            call_config=_decode_method_config(data.get("call_config", {})),
        )


def _encode_method_config(mc: MethodConfig) -> dict[str, Any]:
    return {k: v.name for k, v in mc.__dict__.items() if v != CallConfig.NEVER}


def _decode_method_config(data: dict[str, Any]) -> MethodConfig:
    return MethodConfig(**{k: CallConfig[v] for k, v in data.items()})


def _encode_source(teal_text: str) -> str:
    return base64.b64encode(teal_text.encode()).decode("utf8")


def _decode_source(b64_text: str) -> str:
    return base64.b64decode(b64_text).decode("utf8")


def _encode_state_schema(schema: StateSchema) -> dict[str, int]:
    return {
        "num_byte_slices": schema.num_byte_slices,
        "num_uints": schema.num_uints,
    }


def _decode_state_schema(data: dict[str, int]) -> StateSchema:
    return StateSchema(
        num_byte_slices=data.get("num_byte_slices", 0),
        num_uints=data.get("num_uints", 0),
    )


@dataclasses.dataclass(kw_only=True)
class ApplicationSpecification:
    approval_program: str
    approval_sourcemap: PyTealSourceMap | None
    clear_program: str
    clear_sourcemap: PyTealSourceMap | None
    contract: Contract
    hints: dict[str, MethodHints]
    schema: StateDict
    global_state_schema: StateSchema
    local_state_schema: StateSchema
    bare_call_config: MethodConfig

    def dictify(self) -> dict:
        return {
            "hints": {k: v.dictify() for k, v in self.hints.items() if not v.empty()},
            "source": {
                "approval": _encode_source(self.approval_program),
                "clear": _encode_source(self.clear_program),
            },
            "state": {
                "global": _encode_state_schema(self.global_state_schema),
                "local": _encode_state_schema(self.local_state_schema),
            },
            "schema": self.schema,
            "contract": self.contract.dictify(),
            "bare_call_config": _encode_method_config(self.bare_call_config),
        }

    def to_json(self) -> str:
        return json.dumps(self.dictify(), indent=4)

    @staticmethod
    def from_json(application_spec: str) -> "ApplicationSpecification":
        json_spec = json.loads(application_spec)
        return ApplicationSpecification(
            approval_program=_decode_source(json_spec["source"]["approval"]),
            approval_sourcemap=None,
            clear_program=_decode_source(json_spec["source"]["clear"]),
            clear_sourcemap=None,
            schema=json_spec["schema"],
            global_state_schema=_decode_state_schema(json_spec["state"]["global"]),
            local_state_schema=_decode_state_schema(json_spec["state"]["local"]),
            contract=Contract.undictify(json_spec["contract"]),
            hints={k: MethodHints.undictify(v) for k, v in json_spec["hints"].items()},
            bare_call_config=_decode_method_config(
                json_spec.get("bare_call_config", {})
            ),
        )

    def export(self, directory: Path | str | None = None) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory(optional): path to the directory where the artifacts should be written
        """
        if directory is None:
            output_dir = Path.cwd()
        else:
            output_dir = Path(directory)
            output_dir.mkdir(exist_ok=True, parents=True)

        (output_dir / "approval.teal").write_text(self.approval_program)
        (output_dir / "clear.teal").write_text(self.clear_program)
        (output_dir / "contract.json").write_text(
            json.dumps(self.contract.dictify(), indent=4)
        )
        (output_dir / "application.json").write_text(self.to_json())
