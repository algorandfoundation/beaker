from pyteal import (
    abi,
    TealType,
    Expr,
    TealTypeError,
    BoxGet,
    Seq,
    Assert,
    BoxPut,
    BoxDelete,
)


class Mapping:
    """Mapping is an interface to create a new box per map key"""

    def __init__(self, key_type: type[abi.BaseType], value_type: type[abi.BaseType]):
        self.key_type = key_type
        self.value_type = value_type

    def __getitem__(self, idx: abi.BaseType | Expr) -> "MapElement":
        match idx:
            case abi.BaseType():
                return MapElement(idx.encode(), self.value_type)
            case Expr():
                if idx.type_of() != TealType.bytes:
                    raise TealTypeError(idx.type_of(), TealType.bytes)
                return MapElement(idx, self.value_type)


class MapElement:
    def __init__(self, key: Expr, value_type: type[abi.BaseType]):
        # assert key.type_of() == TealType.bytes, TealTypeError(
        #     key.type_of(), TealType.bytes
        # )

        self.key = key
        self.value_type = value_type

    def store_into(self, val: abi.BaseType) -> Expr:
        # Assert same type, compile time check
        return val.decode(self.get())

    def get(self) -> Expr:
        return Seq(maybe := BoxGet(self.key), Assert(maybe.hasValue()), maybe.value())

    def set(self, val: abi.BaseType | Expr) -> Expr:
        # TODO: does BoxPut work if it needs to be resized later?
        match val:
            case abi.BaseType():
                return BoxPut(self.key, val.encode())
            case Expr():
                if val.type_of() != TealType.bytes:
                    raise TealTypeError(val.type_of(), TealType.bytes)
                return BoxPut(self.key, val)

    def delete(self) -> Expr:
        return BoxDelete(self.key)
