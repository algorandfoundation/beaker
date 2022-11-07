from pyteal import abi, Int, BoxCreate, BoxExtract, Expr, BoxReplace, Bytes, TealType


class List:
    """List stores a list of static types in a box, named as the class attribute unless an overriding name is provided"""

    def __init__(
        self, value_type: type[abi.BaseType], elements: int, name: str = None
    ):
        ts = abi.type_spec_from_annotation(value_type)

        assert not ts.is_dynamic(), "Expected static type for value"
        assert (
            ts.byte_length_static() * elements < 32e3
        ), "Cannot be larger than MAX_BOX_SIZE"

        if name is not None:
            self.name = Bytes(name)  # type: ignore

        self.value_type = ts

        self._element_size = ts.byte_length_static()
        self.element_size = Int(self._element_size)

        self._elements = elements
        self.elements = Int(self._elements)

        self._box_size = self._element_size * self._elements

    def create(self) -> Expr:
        return BoxCreate(self.name, self.element_size * self.elements)

    def __getitem__(self, idx: Int) -> "ListElement":
        return ListElement(self.name, self.element_size, idx)


class ListElement(Expr):
    def __init__(self, name, size, idx):
        self.name = name
        self.size = size
        self.idx = idx

    def store_into(self, val: abi.BaseType) -> Expr:
        return val.decode(self.get())

    def get(self) -> Expr:
        return BoxExtract(self.name, self.size * self.idx, self.size)

    def set(self, val: abi.BaseType) -> Expr:
        return BoxReplace(self.name, self.size * self.idx, val.encode())

    def __str__(self) -> str:
        return f"List Element: {self.name}"

    def __teal__(self, compile_options):
        return self.get().__teal__(compile_options)

    def has_return(self):
        return False

    def type_of(self):
        return TealType.bytes
