import pytest
import pyteal as pt
from .application_schema import *

options = pt.CompileOptions(mode=pt.Mode.Application, version=6)

LOCAL_VAL_TESTS = [
    # key, stacktype, default, val to set, expected error
    (Bytes("k"), pt.TealType.uint64, Int(1), Int(1), None),
    (Bytes("k"), pt.TealType.uint64, None, Int(1), None),
    (Bytes("k"), pt.TealType.uint64, None, Bytes("abc"), pt.TealTypeError),
    (Int(123), pt.TealType.uint64, None, Int(1), pt.TealTypeError),
    (Bytes("k"), pt.TealType.bytes, None, Bytes("abc"), None),
    (Bytes("k"), pt.TealType.bytes, Bytes("abc"), Bytes("def"), None),
    (Bytes("k"), pt.TealType.bytes, Bytes("abc"), Bytes("def"), None),
    (Bytes("k"), pt.TealType.bytes, None, Int(1), pt.TealTypeError),
    (Int(123), pt.TealType.bytes, None, Bytes("abc"), pt.TealTypeError),
]

DYNAMIC_VALUE_TESTS = [
    # stack type, max keys, key gen, key_seed, val, expected error
    (pt.TealType.uint64, 1, None, Bytes("abc"), Int(1), None),
    (pt.TealType.bytes, 1, None, Bytes("abc"), Bytes("abc"), None),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.bytes)(lambda v: pt.Substring(v, Int(0), Int(1))),
        Bytes("abc"),
        Bytes("abc"),
        None,
    ),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.uint64)(lambda v: Int(1)),
        Bytes("abc"),
        Bytes("abc"),
        pt.TealTypeError,
    ),
    (pt.TealType.uint64, 1, None, Bytes("abc"), Bytes("abc"), pt.TealTypeError),
    (pt.TealType.bytes, 1, None, Bytes("abc"), Int(1), pt.TealTypeError),
    (pt.TealType.uint64, 0, None, Bytes("abc"), Int(1), Exception),
    (pt.TealType.uint64, 17, None, Bytes("abc"), Int(1), Exception),
]


def get_default_for_type(stack_type, default):
    expected_default = default
    if expected_default is None:
        if stack_type == pt.TealType.bytes:
            expected_default = Bytes("")
        else:
            expected_default = Int(0)
    return expected_default


@pytest.mark.parametrize("key, stack_type, default, val, error", LOCAL_VAL_TESTS)
def test_local_value(key, stack_type, default, val, error):
    if error is not None:
        with pytest.raises(error):
            do_lv_test(key, stack_type, default, val)
    else:
        do_lv_test(key, stack_type, default, val)


def do_lv_test(key, stack_type, default, val):
    lv = LocalStateValue(stack_type=stack_type, key=key, default=default)

    actual = lv.set(pt.Txn.sender(), val).__teal__(options)
    expected = pt.App.localPut(pt.Txn.sender(), key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.set_default(pt.Txn.sender()).__teal__(options)
    expected_default = get_default_for_type(stack_type, default)
    expected = pt.App.localPut(pt.Txn.sender(), key, expected_default).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localGetEx(pt.Txn.sender(), Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    # TODO: other get_*

    actual = lv.delete(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localDel(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


@pytest.mark.parametrize(
    "stack_type, max_keys, key_gen, key_seed, val, error", DYNAMIC_VALUE_TESTS
)
def test_dynamic_local_value(stack_type, max_keys, key_gen, key_seed, val, error):
    if error is not None:
        with pytest.raises(error):
            do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val)
    else:
        do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val)


def do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val):
    dlv = DynamicLocalStateValue(
        stack_type=stack_type, max_keys=max_keys, key_gen=key_gen
    )

    lv = dlv(key_seed)

    key = key_seed
    if key_gen is not None:
        key = key_gen(key_seed)

    actual = lv.set(pt.Txn.sender(), val).__teal__(options)
    expected = pt.App.localPut(pt.Txn.sender(), key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.set_default(pt.Txn.sender()).__teal__(options)
    expected_default = get_default_for_type(stack_type, None)
    expected = pt.App.localPut(pt.Txn.sender(), key, expected_default).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localGetEx(pt.Txn.sender(), Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    # TODO: other get_*

    actual = lv.delete(pt.Txn.sender()).__teal__(options)
    expected = pt.App.localDel(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_account_state():
    pass


def test_global_value():
    pass


def test_dynamic_global_value():
    pass


def test_application_state():
    pass
