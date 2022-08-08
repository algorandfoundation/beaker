import pytest
from typing import Literal
import pyteal as pt
from beaker.struct import Struct


def test_valid_create():
    with pytest.raises(Exception):
        Struct()

    with pytest.raises(Exception):

        class A(Struct):
            a: pt.abi.Uint64

        class B(A):
            b: pt.abi.Uint64

        B()


class UserId(Struct):
    user: pt.abi.Address
    id: pt.abi.Uint64


class Order(Struct):
    items: pt.abi.DynamicArray[pt.abi.String]
    id: pt.abi.Uint32
    flags: pt.abi.StaticArray[pt.abi.Bool, Literal[32]]


class SubOrder(Struct):
    order: Order
    idx: pt.abi.Uint8


MODEL_TESTS = [
    (
        UserId(),
        pt.abi.Tuple2[pt.abi.Address, pt.abi.Uint64],
        ["user", "id"],
        {"user": pt.abi.Address().type_spec(), "id": pt.abi.Uint64().type_spec()},
        "(address,uint64)",
    ),
    (
        Order(),
        pt.abi.Tuple3[
            pt.abi.DynamicArray[pt.abi.String],
            pt.abi.Uint32,
            pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
        ],
        ["items", "id", "flags"],
        {
            "items": pt.abi.make(pt.abi.DynamicArray[pt.abi.String]).type_spec(),
            "id": pt.abi.Uint32().type_spec(),
            "flags": pt.abi.make(
                pt.abi.StaticArray[pt.abi.Bool, Literal[32]]
            ).type_spec(),
        },
        "(string[],uint32,bool[32])",
    ),
    (
        SubOrder(),
        pt.abi.Tuple2[
            pt.abi.Tuple3[
                pt.abi.DynamicArray[pt.abi.String],
                pt.abi.Uint32,
                pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
            ],
            pt.abi.Uint8,
        ],
        ["order", "idx"],
        {
            "order": pt.abi.make(
                pt.abi.Tuple3[
                    pt.abi.DynamicArray[pt.abi.String],
                    pt.abi.Uint32,
                    pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
                ]
            ).type_spec(),
            "idx": pt.abi.Uint8().type_spec(),
        },
        "((string[],uint32,bool[32]),uint8)",
    ),
]


@pytest.mark.parametrize(
    "model, annotation_type, field_names, type_specs, strified", MODEL_TESTS
)
def test_model_create(
    model: Struct, annotation_type, field_names, type_specs, strified
):

    assert model.annotation_type() == annotation_type
    assert model.field_names == field_names
    assert model.type_specs == type_specs
    assert model.__str__() == strified
    assert model.type_spec() == pt.abi.type_spec_from_annotation(annotation_type)


MODEL_SET_TESTS = [
    (UserId(), [pt.abi.Address(), pt.abi.Uint64()], None),
    (UserId(), [pt.abi.Address()], pt.TealInputError),
    (UserId(), [pt.abi.Address(), pt.abi.Uint8()], pt.TealTypeError),
    (UserId(), [pt.abi.Address(), pt.Int(1)], None),
    (UserId(), [pt.abi.Address(), pt.Bytes("00")], pt.TealTypeError),
    (UserId(), [pt.abi.Address(), 1], pt.TealTypeError),
    (
        Order(),
        [
            pt.abi.make(pt.abi.DynamicArray[pt.abi.String]),
            pt.abi.Uint32(),
            pt.abi.make(pt.abi.StaticArray[pt.abi.Bool, Literal[32]]),
        ],
        None,
    ),
    (
        SubOrder(),
        [
            pt.abi.make(
                pt.abi.Tuple3[
                    pt.abi.DynamicArray[pt.abi.String],
                    pt.abi.Uint32,
                    pt.abi.StaticArray[pt.abi.Bool, Literal[32]],
                ]
            ),
            pt.abi.Uint8(),
        ],
        None,
    ),
]


@pytest.mark.parametrize("model, vals, exception", MODEL_SET_TESTS)
def test_model_set(model: Struct, vals, exception):
    if exception is not None:
        with pytest.raises(exception):
            model.set(*vals)
    else:
        model.set(*vals)


def test_model_codec():
    class CodecTest(Struct):
        a: pt.abi.Uint64
        b: pt.abi.DynamicArray[pt.abi.Uint8]
        c: pt.abi.Tuple2[pt.abi.Bool, pt.abi.Bool]

    c = CodecTest()
    to_encode = {"a": 1, "b": [1, 2, 3], "c": [True, False]}
    encoded = c.client_encode(to_encode)
    decoded = c.client_decode(encoded)
    assert to_encode == decoded, "The result of decode(encode(data)) should == data"
