import base64
from typing import Any
from beaker.application import Application
from beaker.state import ApplicationState, AccountState


class ApplicationSource:
    def __init__(self, approval: str, clear: str) -> None:
        self._approval = base64.b64encode(approval.encode()).decode("utf8")
        self._clear = base64.b64encode(clear.encode()).decode("utf8")

    def dictify(self) -> dict[str, str]:
        return {"approval": self._approval, "clear": self._clear}


class ApplicationSchema:
    def __init__(self, app_state: ApplicationState, acct_state: AccountState) -> None:
        self._global = app_state
        self._local = acct_state

    def dictify(self) -> dict[str, Any]:
        return {
            "local": self._local.dictify(),
            "global": self._global.dictify(),
        }


class ApplicationSpec:
    def __init__(self, app: Application) -> None:
        if app.approval_program is None or app.clear_program is None:
            raise Exception(
                "approval or clear program are not built, please build the programs first"
            )

        self.source = ApplicationSource(app.approval_program, app.clear_program)
        self.schema = ApplicationSchema(app.app_state, app.acct_state)
        self.contract = app.contract
        self.hints = app.hints

        # Dedupe structs
        self.structs: dict[str, list[tuple[str, str]]] = {}
        for v in self.hints.values():
            if v.structs is None:
                continue

            for s in v.structs.values():
                self.structs[s.name] = s.elements

    def dictify(self) -> dict[str, Any]:
        """returns a dictionary, helpful to provide to callers with information about the application specification"""
        return {
            "hints": {k: v.dictify() for k, v in self.hints.items() if not v.empty()},
            "structs": self.structs,
            "source": self.source.dictify(),
            "schema": self.schema.dictify(),
            "contract": self.contract.dictify(),
        }


# ```
# add types section, define types once using the list of fields w/ name and type
# consider specifying the type as `ref:TheType` to avoid future breakage with arc defined types vs user defined
# consider tweaking the `default args` to reference state field (or methods) directly from json defs
# move contract elements (name, methods, ...) into root
# consider removing `static` from Declared schema
# ```

# ```ts
#
# export interface AppSpec {
#  hints: Record<string, HintSpec>;
#  schema: SchemaSpec;
#  source: AppSources;
#  contract: algosdk.ABIContract;
# }
#
# export interface HintSpec {
#  structs: Record<string, Struct>;
#  readonly: boolean;
#  default_arguments: Record<string, DefaultArgument>;
# }
#
# type StructElement = [string, string];
#
# export interface Struct {
#  name: string;
#  elements: StructElement[];
# }
#
# export interface DefaultArgument {
#  source: string;
#  data: string | bigint | number;
# }
#
# export enum AVMType {
#  uint64,
#  bytes,
# }
#
