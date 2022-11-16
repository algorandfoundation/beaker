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
    Concat,
)


class Mapping:
    """Mapping provides an abstraction to store some typed data in a box keyed with a typed key"""

    def __init__(
        self,
        key_type: type[abi.BaseType],
        value_type: type[abi.BaseType],
        prefix: Expr | None = None,
    ):
        self._key_type = key_type
        self._key_type_spec = abi.type_spec_from_annotation(key_type)

        self._value_type = value_type
        self._value_type_spec = abi.type_spec_from_annotation(value_type)

        if isinstance(prefix, Expr) and prefix.type_of() != TealType.bytes:
            raise TealTypeError(prefix.type_of(), TealType.bytes)

        self.prefix = prefix

    def _prefix_key(self, key: Expr) -> Expr:
        if self.prefix is not None:
            return Concat(self.prefix, key)
        return key

    def __getitem__(self, key: abi.BaseType | Expr) -> "MapElement":
        match key:
            case abi.BaseType():
                if key.type_spec() != self._key_type_spec:
                    raise TealTypeError(key.type_spec(), self._key_type_spec)
                return MapElement(self._prefix_key(key.encode()), self._value_type)
            case Expr():
                if key.type_of() != TealType.bytes:
                    raise TealTypeError(key.type_of(), TealType.bytes)
                return MapElement(self._prefix_key(key), self._value_type)


class MapElement:
    """Container type for a specific box key and type"""

    def __init__(self, key: Expr, value_type: type[abi.BaseType]):
        assert key.type_of() == TealType.bytes, TealTypeError(
            key.type_of(), TealType.bytes
        )

        self.key = key
        self._value_type = value_type

    def exists(self) -> Expr:
        return Seq(maybe := BoxGet(self.key), maybe.hasValue())

    def store_into(self, val: abi.BaseType) -> Expr:
        return val.decode(self.get())

    def get(self) -> Expr:
        return Seq(maybe := BoxGet(self.key), Assert(maybe.hasValue()), maybe.value())

    def set(self, val: abi.BaseType | Expr) -> Expr:
        match val:
            case abi.BaseType():
                if not isinstance(val, self._value_type):
                    raise TealTypeError(val.__class__, self._value_type)
                return Seq(
                    # delete the old one
                    Pop(BoxDelete(self.key)),
                    # write the new one
                    BoxPut(self.key, val.encode()),
                )
            case Expr():
                if val.type_of() != TealType.bytes:
                    raise TealTypeError(val.type_of(), TealType.bytes)
                return BoxPut(self.key, val)

    def delete(self) -> Expr:
        return BoxDelete(self.key)
