from typing import Any
from base64 import b64decode


def str_or_hex(v: bytes) -> str:
    decoded: str = ""
    try:
        decoded = v.decode("utf-8")
    except Exception:
        decoded = f"0x{v.hex()}"

    return decoded


def decode_state(
    state: list[dict[str, Any]], force_str=False
) -> dict[bytes | str, bytes | str | int]:

    decoded_state: dict[bytes | str, str | int] = {}

    for sv in state:

        raw_key = b64decode(sv["key"])
        key = str_or_hex(raw_key) if force_str else raw_key

        match sv["value"]["type"]:
            case 1:
                raw_val = b64decode(sv["value"]["bytes"])
                val = str_or_hex(raw_val) if force_str else raw_val
            case 2:
                val = sv["value"]["uint"]

        decoded_state[key] = val
    return decoded_state
