from pyteal import *


class ListElement:
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


class Listing:
    def __init__(self, name: Bytes, value_type: type[abi.BaseType], elements: int):
        ts = abi.type_spec_from_annotation(value_type)

        assert not ts.is_dynamic(), "Expected static type for value"
        assert ts.byte_length_static() * elements < 32e3, "Cannot be larger than MAX_BOX_SIZE"

        self.name = name
        self.value_type = ts

        self._element_size = ts.byte_length_static()
        self.element_size = Int(self._element_size)

        self._elements = elements
        self.elements = Int(self._elements)

    def create(self) -> Expr:
        return BoxCreate(self.name, self.element_size * self.elements)

    def __getitem__(self, idx: Int) -> ListElement:
        return ListElement(self.name, self.element_size, idx)
