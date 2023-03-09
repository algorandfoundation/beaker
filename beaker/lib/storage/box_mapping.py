from pyteal import (
    Assert,
    BoxDelete,
    BoxGet,
    BoxLen,
    BoxPut,
    Concat,
    Expr,
    Pop,
    Seq,
    TealType,
    TealTypeError,
    abi,
)
from pyteal.types import require_type


class BoxMapping:
    """Mapping provides an abstraction to store some typed data in a box keyed with a typed key"""

    def __init__(
        self,
        key_type: type[abi.BaseType],
        value_type: type[abi.BaseType],
        prefix: Expr | None = None,
    ):
        """Initialize a Mapping object with details about storage

        Args:
            key_type: The type that will be used for the key. This type *MUST* encode to a byte string of < 64 bytes or it will fail at runtime.
            value_type:  The type to be stored in the box.
            prefix (Optional): An optional argument to prefix the key, providing a name space in order to avoid collisions with other mappings using the same keys
        """
        self._key_type = key_type
        self._key_type_spec = abi.type_spec_from_annotation(key_type)

        self._value_type = value_type
        self._value_type_spec = abi.type_spec_from_annotation(value_type)

        if prefix is not None:
            require_type(prefix, TealType.bytes)

        self.prefix = prefix

    def _prefix_key(self, key: Expr) -> Expr:
        if self.prefix is not None:
            return Concat(self.prefix, key)
        return key

    class Element:
        """Container type for a specific box key and type"""

        def __init__(self, key: Expr, value_type: type[abi.BaseType]):
            require_type(key, TealType.bytes)

            self.key = key
            self._value_type = value_type

        def exists(self) -> Expr:
            """check to see if a box with this key exists."""
            return Seq(maybe := BoxLen(self.key), maybe.hasValue())

        def store_into(self, val: abi.BaseType) -> Expr:
            """decode the bytes from this box into an abi type.

            Args:
                val: An instance of the type to be populated with the bytes from the box
            """
            return val.decode(self.get())

        def get(self) -> Expr:
            """get the bytes from this box."""
            return Seq(
                maybe := BoxGet(self.key), Assert(maybe.hasValue()), maybe.value()
            )

        def set(self, val: abi.BaseType | Expr) -> Expr:
            """overwrites the contents of the box with the provided value.

            Args:
                val: An instance of the type or an Expr that evaluates to bytes
            """
            match val:
                case abi.BaseType():
                    if not isinstance(val, self._value_type):
                        raise TealTypeError(val.__class__, self._value_type)
                    bytes_val = val.encode()
                case Expr():
                    require_type(val, TealType.bytes)
                    bytes_val = val
                case _:
                    raise TealTypeError(type(val), Expr | abi.BaseType)
            return Seq(
                Pop(BoxDelete(self.key)),
                BoxPut(self.key, bytes_val),
            )

        def delete(self) -> Expr:
            """delete the box at this key"""
            return BoxDelete(self.key)

    def __getitem__(self, key: abi.BaseType | Expr) -> Element:
        match key:
            case abi.BaseType():
                if key.type_spec() != self._key_type_spec:
                    raise TealTypeError(key.type_spec(), self._key_type_spec)
                key = key.encode()
            case Expr():
                require_type(key, TealType.bytes)
            case _:
                raise TealTypeError(type(key), Expr | abi.BaseType)

        return self.Element(self._prefix_key(key), self._value_type)
