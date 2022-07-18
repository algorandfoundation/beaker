from typing import Any
from base64 import b64decode


def str_or_hex(v: bytes):
    try:
        v = v.decode("utf-8")
    except Exception:
        v = f"0x{v.hex()}"
    return v


def decode_state(
    state: list[dict[str, Any]], force_str=False
) -> dict[bytes | str, bytes | str | int]:
    decoded_state: dict[str, str | int] = {}
    for sv in state:
        key = b64decode(sv["key"])
        if force_str:
            key = str_or_hex(key)

        match sv["value"]["type"]:
            case 1:
                val = b64decode(sv["value"]["bytes"])
                if force_str:
                    val = str_or_hex(val)
            case 2:
                val = sv["value"]["uint"]
            case _:
                val = None

        decoded_state[key] = val
    return decoded_state
