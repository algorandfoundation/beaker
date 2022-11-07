from pyteal import (
    abi,
    TealType,
    Expr,
    TealTypeError,
    Seq,
    Assert,
    BoxPut,
    BoxDelete,
    BoxGet,
    Pop,
)


class Mapping:
    """Mapping is an interface to create a new box per map key"""

    def __init__(self, key_type: type[abi.BaseType], value_type: type[abi.BaseType]):

        self._key_type = key_type
        self._key_type_spec = abi.type_spec_from_annotation(key_type)

        self._value_type = value_type
        self._value_type_spec = abi.type_spec_from_annotation(value_type)


    def __getitem__(self, idx: abi.BaseType | Expr) -> "MapElement":
        match idx:
            case abi.BaseType():
                assert idx.type_spec() == self._key_type_spec
                return MapElement(idx.encode(), self._value_type)
            case Expr():
                if idx.type_of() != TealType.bytes:
                    raise TealTypeError(idx.type_of(), TealType.bytes)
                return MapElement(idx, self._value_type)


class MapElement:
    def __init__(self, key: Expr, value_type: type[abi.BaseType]):
        assert key.type_of() == TealType.bytes, TealTypeError(
            key.type_of(), TealType.bytes
        )

        self.key = key
        self._value_type = value_type

    def store_into(self, val: abi.BaseType) -> Expr:
        return val.decode(self.get())

    def get(self) -> Expr:
        return Seq(maybe := BoxGet(self.key), Assert(maybe.hasValue()), maybe.value())

    def set(self, val: abi.BaseType | Expr) -> Expr:
        match val:
            case abi.BaseType():
                return Seq(
                    # delete the old one
                    Pop(BoxDelete(self.key)),
                    # write the new one
                    BoxPut(self.key, val.encode())
                )
            case Expr():
                if val.type_of() != TealType.bytes:
                    raise TealTypeError(val.type_of(), TealType.bytes)
                return BoxPut(self.key, val)

    def delete(self) -> Expr:
        return BoxDelete(self.key)
