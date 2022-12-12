import pyteal as pt


class Box:
    def __init__(self, name: str, size: int):
        self._name = name
        self.name = pt.Bytes(name)

        self._size = size
        self.size = pt.Int(size)

    def create(self) -> pt.Expr:
        return pt.Pop(pt.BoxCreate(self.name, self.size))

    def length(self) -> pt.Expr:
        return pt.Seq(box_length := pt.BoxLen(self.name), box_length.value())

    def exists(self) -> pt.Expr:
        return pt.Seq(box_length := pt.BoxLen(self.name), box_length.hasValue())

    def read(self, start: pt.Expr, stop: pt.Expr) -> pt.Expr:
        return pt.BoxExtract(self.name, start, stop)

    def write(self, start: pt.Expr, value: pt.Expr) -> pt.Expr:
        return pt.BoxReplace(start, value)

    def __getitem__(self, idx: pt.Expr) -> pt.Expr:
        pass
