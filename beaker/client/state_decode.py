from typing import Any
from base64 import b64decode


def str_or_hex(v: bytes) -> str:
    decoded: str = ""
    try:
        decoded = v.decode("utf-8")
    except Exception:
        decoded = v.hex()

    return decoded


def decode_state(
    state: list[dict[str, Any]], raw: bool = False
) -> dict[str | bytes, bytes | str | int | None]:

    decoded_state: dict[str | bytes, bytes | str | int | None] = {}

    for sv in state:

        raw_key = b64decode(sv["key"])

        key: str | bytes = raw_key if raw else str_or_hex(raw_key)
        val: str | bytes | int | None

        action = (
            sv["value"]["action"] if "action" in sv["value"] else sv["value"]["type"]
        )

        match action:
            case 1:
                raw_val = b64decode(sv["value"]["bytes"])
                val = raw_val if raw else str_or_hex(raw_val)
            case 2:
                val = sv["value"]["uint"]
            case 3:
                val = None

        decoded_state[key] = val
    return decoded_state
