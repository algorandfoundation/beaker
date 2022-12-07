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
                """
                approval or clear program are not built, please build the programs first
                """
            )

        self.source = ApplicationSource(app.approval_program, app.clear_program)
        self.schema = ApplicationSchema(app.app_state, app.acct_state)
        self.contract = app.contract

        self.hints = app.hints

        # Gather custom types
        self.types: dict[str, list[tuple[str, str]]] = {}
        for k, v in self.hints.items():
            if v.structs is None:
                continue

            for s in v.structs.values():
                self.types[s.name] = s.elements

            # wipe the structs from the hints
            self.hints[k].structs = None

        # TODO:

        # Specify the method argument type alias as the type as `ref:TheType` to
        # avoid future breakage with arc defined types vs user defined

        # Change the `default args` to be part of the method spec and reference
        # the state field (or methods) directly like `ref:the_key` spec

    def dictify(self) -> dict[str, Any]:
        """
        returns a dictionary, helpful to provide to callers with
        information about the application specification
        """
        return {
            "hints": {k: v.dictify() for k, v in self.hints.items() if not v.empty()},
            "types": self.types,
            "source": self.source.dictify(),
            "schema": self.schema.dictify(),
        } | self.contract.dictify()
