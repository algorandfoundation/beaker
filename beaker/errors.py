class BareOverwriteError(Exception):
    def __init__(self, on_complete: str):
        self.on_complete = on_complete

    def __str__(self) -> str:
        return (
            f"Tried to overwrite a bare external: {self.on_complete}.\n"
            + "If you're trying to override a default method in Application"
            + ", be sure to use the same name as the method defined (`create`, `update`, `delete`)."
        )
