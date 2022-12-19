from pyteal import (
    abi,
    Int,
    BoxCreate,
    BoxExtract,
    Expr,
    BoxReplace,
    Bytes,
    TealType,
    TealTypeError,
    TealBlock,
    TealSimpleBlock,
    CompileOptions,
)


class List:
    """List stores a list of static types in a box, named as the class attribute unless an overriding name is provided"""

    def __init__(
        self, value_type: type[abi.BaseType], elements: int, name: str | None = None
    ):
        ts = abi.type_spec_from_annotation(value_type)

        assert not ts.is_dynamic(), "Expected static type for value"
        assert (
            ts.byte_length_static() * elements < 32e3
        ), "Cannot be larger than MAX_BOX_SIZE"

        # Will be set later if its part of an Application
        self.name: Expr | None = None
        if name is not None:
            self.name = Bytes(name)

        self.value_type = ts

        self._element_size = ts.byte_length_static()
        self.element_size = Int(self._element_size)

        self._elements = elements
        self.elements = Int(self._elements)

        self._box_size = self._element_size * self._elements
        self.box_size = Int(self._box_size)

    def create(self) -> Expr:
        """creates a box with the given name and with a size that will allow storage of the number of the element specified."""
        assert self.name is not None
        return BoxCreate(self.name, self.box_size)

    def __getitem__(self, idx: Expr) -> "ListElement":
        assert self.name is not None
        return ListElement(self.name, self.element_size, idx)


class ListElement(Expr):
    def __init__(self, name: Expr, element_size: Expr, idx: Expr):
        if name.type_of() != TealType.bytes:
            raise TealTypeError(name.type_of(), TealType.bytes)

        if element_size.type_of() != TealType.uint64:
            raise TealTypeError(element_size.type_of(), TealType.uint64)

        if element_size.type_of() != TealType.uint64:
            raise TealTypeError(idx.type_of(), TealType.uint64)

        self.name = name
        self.element_size = element_size
        self.idx = idx

    def store_into(self, val: abi.BaseType) -> Expr:
        """decode the bytes from this list element into the instance of the type provided

        Args:
            val: An instance of the type to decode into
        """
        return val.decode(self.get())

    def get(self) -> Expr:
        """get the bytes for this element in the list"""
        return BoxExtract(self.name, self.element_size * self.idx, self.element_size)

    def set(self, val: abi.BaseType) -> Expr:
        """set the bytes for this element in the list

        Args:
            The value to write into the list at the given index
        """
        return BoxReplace(self.name, self.element_size * self.idx, val.encode())

    def __str__(self) -> str:
        return f"List Element: {self.name}[{self.idx}]"

    def __teal__(
        self, compile_options: CompileOptions
    ) -> tuple[TealBlock, TealSimpleBlock]:
        return self.get().__teal__(compile_options)

    def has_return(self) -> bool:
        return False

    def type_of(self) -> TealType:
        return TealType.bytes
