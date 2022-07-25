import inspect
from typing import Any
from typing import cast
from pyteal import Expr, abi, TealInputError, TealTypeError, Seq


class Struct(abi.Tuple):
    """Struct provides a base class to inherit from when defining custom data structures"""

    def __init__(self):
        if not hasattr(self, "__annotations__"):
            raise Exception("Expected fields to be declared but found none")

        if self.__class__.__base__ is not Struct:
            raise Exception("Expected direct subclass of Struct")

        self.type_specs = {
            k: cast(abi.BaseType, abi.make(v)).type_spec()
            if not (inspect.isclass(v) and issubclass(v, Struct))
            else v().type_spec()
            for k, v in self.__annotations__.items()
        }
        self.field_names = list(self.type_specs.keys())

        super().__init__(abi.TupleTypeSpec(*self.type_specs.values()))

        for idx in range(len(self.field_names)):
            name = self.field_names[idx]
            setattr(self, name, self.__getitem__(idx))

        self.sdk_codec = abi.algosdk_from_type_spec(self.type_spec())

    def set(
        self, *exprs: Expr | abi.BaseType | abi.TupleElement | abi.ComputedValue
    ) -> Expr:
        abi_types: list[abi.BaseType] = []
        setters: list[Expr] = []

        if len(exprs) != len(self.field_names):
            raise TealInputError(
                f"Expected {len(self.field_names)} items to set, got: {len(exprs)}"
            )

        for idx, e in enumerate(exprs):
            tspec: abi.TypeSpec = self.type_specs[self.field_names[idx]]

            match e:
                case abi.TupleElement() | abi.ComputedValue():
                    if e.produced_type_spec() != tspec:
                        raise TealTypeError(tspec, e.produced_type_spec())
                    setters.append(e.store_into(val := tspec.new_instance()))
                    abi_types.append(val)
                case abi.BaseType():
                    if e.type_spec() != tspec:
                        raise TealTypeError(tspec, e.type_spec())
                    abi_types.append(e)
                case Expr():
                    if e.type_of() != tspec.storage_type():
                        raise TealTypeError(tspec.storage_type(), e.type_of())
                    setters.append((val := tspec.new_instance()).stored_value.store(e))
                    abi_types.append(val)
                case _:
                    raise TealTypeError(tspec, e)
            abi_types = abi_types

        return Seq(*setters, super().set(*abi_types))

    def annotation_type(self):
        """returns the annotation type for the model, useful for type aliases in method signature annotation"""
        return self.type_spec().annotation_type()

    def client_decode(self, to_decode: bytes) -> dict[str, Any]:
        """decode a bytestring into a dictionary of keys/values based on the fields this model declared"""
        values = self.sdk_codec.decode(bytestring=to_decode)
        return dict(zip(self.field_names, values))

    def client_encode(self, val: dict[str, Any]) -> bytes:
        """encode a dictionary of keys/values to a bytestring matching the ABI tuple type it is represented by"""
        values = [val[name] for name in self.field_names]
        return self.sdk_codec.encode(values)

    def __str__(self) -> str:
        return super().type_spec().__str__()
