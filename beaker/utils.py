from typing import TypeVar, Callable, MutableMapping

TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


# TODO: move/rename this - shouldn't really be exposed
def remove_first_match(
    m: MutableMapping[TKey, TValue], predicate: Callable[[TKey, TValue], bool]
) -> None:
    for k, v in m.items():
        if predicate(k, v):
            del m[k]
            break
