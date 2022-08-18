import pytest
import pyteal as pt
from beaker.state import (
    ApplicationState,
    AccountState,
    DynamicAccountStateValue,
    DynamicApplicationStateValue,
    ApplicationStateValue,
    AccountStateValue,
    get_default_for_type,
)

options = pt.CompileOptions(mode=pt.Mode.Application, version=6)

ACCOUNT_VAL_TESTS = [
    # key, stacktype, default, val to set, expected error
    (pt.Bytes("k"), pt.TealType.uint64, pt.Int(1), pt.Int(1), None),
    (pt.Bytes("k"), pt.TealType.uint64, None, pt.Int(1), None),
    (pt.Bytes("k"), pt.TealType.uint64, None, pt.Bytes("abc"), pt.TealTypeError),
    (pt.Int(123), pt.TealType.uint64, None, pt.Int(1), pt.TealTypeError),
    (pt.Bytes("k"), pt.TealType.bytes, None, pt.Bytes("abc"), None),
    (pt.Bytes("k"), pt.TealType.bytes, pt.Bytes("abc"), pt.Bytes("def"), None),
    (pt.Bytes("k"), pt.TealType.bytes, pt.Bytes("abc"), pt.Bytes("def"), None),
    (pt.Bytes("k"), pt.TealType.bytes, None, pt.Int(1), pt.TealTypeError),
    (pt.Bytes("k"), pt.TealType.bytes, pt.Int(1), pt.Bytes("abc"), pt.TealTypeError),
    (pt.Int(123), pt.TealType.bytes, None, pt.Bytes("abc"), pt.TealTypeError),
    (None, pt.TealType.bytes, None, pt.Bytes("abc"), pt.TealInputError),
]


DYNAMIC_ACCOUNT_VALUE_TESTS = [
    # stack type, max keys, key gen, key_seed, val, expected error
    (pt.TealType.uint64, 1, None, pt.Bytes("abc"), pt.Int(1), None),
    (pt.TealType.bytes, 1, None, pt.Bytes("abc"), pt.Bytes("abc"), None),
    (pt.TealType.bytes, 1, None, pt.abi.String(), pt.Bytes("abc"), None),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.bytes)(
            lambda v: pt.Substring(v, pt.Int(0), pt.Int(1))
        ),
        pt.Bytes("abc"),
        pt.Bytes("abc"),
        None,
    ),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.uint64)(lambda v: pt.Int(1)),
        pt.Bytes("abc"),
        pt.Bytes("abc"),
        pt.TealTypeError,
    ),
    (pt.TealType.uint64, 1, None, pt.Bytes("abc"), pt.Bytes("abc"), pt.TealTypeError),
    (pt.TealType.bytes, 1, None, pt.Bytes("abc"), pt.Int(1), pt.TealTypeError),
    (pt.TealType.uint64, 0, None, pt.Bytes("abc"), pt.Int(1), Exception),
    (pt.TealType.uint64, 17, None, pt.Bytes("abc"), pt.Int(1), Exception),
]


@pytest.mark.parametrize("key, stack_type, default, val, error", ACCOUNT_VAL_TESTS)
def test_local_value(key, stack_type, default, val, error):
    if error is not None:
        with pytest.raises(error):
            do_lv_test(key, stack_type, default, val)
    else:
        do_lv_test(key, stack_type, default, val)


def do_lv_test(key, stack_type, default, val):
    lv = AccountStateValue(stack_type=stack_type, key=key, default=default)

    assert lv.__str__() == f"AccountStateValue (Txn Sender) {key}"

    actual = lv.set(val).__teal__(options)
    expected = pt.App.localPut(pt.Txn.sender(), key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.set_default().__teal__(options)
    expected_default = get_default_for_type(stack_type, default)
    expected = pt.App.localPut(pt.Txn.sender(), key, expected_default).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get().__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv[pt.Txn.accounts[1]].get().__teal__(options)
    expected = pt.App.localGet(pt.Txn.accounts[1], key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe().__teal__(options)
    expected = pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    default = get_default_for_type(stack_type=stack_type, default=None)
    actual = lv.get_else(default).__teal__(options)
    expected = pt.If(
        (v := pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key)).hasValue(),
        v.value(),
        default,
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.get_must().__teal__(options)
    expected = pt.Seq(
        (v := pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key)),
        pt.Assert(v.hasValue()),
        v.value(),
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.delete().__teal__(options)
    expected = pt.App.localDel(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.delete().__teal__(options)
    expected = pt.App.localDel(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


@pytest.mark.parametrize(
    "stack_type, max_keys, key_gen, key_seed, val, error", DYNAMIC_ACCOUNT_VALUE_TESTS
)
def test_dynamic_local_value(stack_type, max_keys, key_gen, key_seed, val, error):
    if error is not None:
        with pytest.raises(error):
            do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val)
    else:
        do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val)


def do_dynamic_lv_test(stack_type, max_keys, key_gen, key_seed, val):
    dlv = DynamicAccountStateValue(
        stack_type=stack_type, max_keys=max_keys, key_gen=key_gen
    )

    lv = dlv[key_seed]

    key = key_seed
    if isinstance(key, pt.abi.BaseType):
        key = key.encode()
    if key_gen is not None:
        key = key_gen(key_seed)

    actual = lv.set(val).__teal__(options)
    expected = pt.App.localPut(pt.Txn.sender(), key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.set_default().__teal__(options)
    expected_default = get_default_for_type(stack_type, None)
    expected = pt.App.localPut(pt.Txn.sender(), key, expected_default).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get().__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.__teal__(options)
    expected = pt.App.localGet(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe().__teal__(options)
    expected = pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    default = get_default_for_type(stack_type=stack_type, default=None)
    actual = lv.get_else(default).__teal__(options)
    expected = pt.If(
        (v := pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key)).hasValue(),
        v.value(),
        default,
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.get_must().__teal__(options)
    expected = pt.Seq(
        (v := pt.App.localGetEx(pt.Txn.sender(), pt.Int(0), key)),
        pt.Assert(v.hasValue()),
        v.value(),
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.delete().__teal__(options)
    expected = pt.App.localDel(pt.Txn.sender(), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


APPLICATION_VAL_TESTS = [
    # key, stacktype, default, val to set, static, expected error
    (pt.Bytes("k"), pt.TealType.uint64, pt.Int(1), pt.Int(1), False, None),
    (pt.Bytes("k"), pt.TealType.uint64, None, pt.Int(1), False, None),
    (pt.Bytes("k"), pt.TealType.uint64, None, pt.Bytes("abc"), False, pt.TealTypeError),
    (pt.Int(123), pt.TealType.uint64, None, pt.Int(1), False, pt.TealTypeError),
    (pt.Bytes("k"), pt.TealType.bytes, None, pt.Bytes("abc"), False, None),
    (pt.Bytes("k"), pt.TealType.bytes, pt.Bytes("abc"), pt.Bytes("def"), False, None),
    (pt.Bytes("k"), pt.TealType.bytes, pt.Bytes("abc"), pt.Bytes("def"), False, None),
    (pt.Bytes("k"), pt.TealType.bytes, None, pt.Int(1), False, pt.TealTypeError),
    (pt.Int(123), pt.TealType.bytes, None, pt.Bytes("abc"), False, pt.TealTypeError),
    (pt.Bytes("k"), pt.TealType.bytes, None, pt.Bytes("abc"), True, pt.TealInputError),
    (None, pt.TealType.bytes, None, pt.Bytes("abc"), False, pt.TealInputError),
]


@pytest.mark.parametrize(
    "key, stack_type, default, val, static, error", APPLICATION_VAL_TESTS
)
def test_global_value(key, stack_type, default, val, static, error):
    if error is not None:
        with pytest.raises(error):
            do_gv_test(key, stack_type, default, val, static)
    else:
        do_gv_test(key, stack_type, default, val, static)


def do_gv_test(key, stack_type, default, val, static):
    lv = ApplicationStateValue(
        stack_type=stack_type, key=key, default=default, static=static
    )

    assert lv.__str__() == f"ApplicationStateValue {key}"

    actual = lv.set(val).__teal__(options)

    if static:
        expected = pt.Seq(
            v := pt.App.globalGetEx(pt.Int(0), key),
            pt.Assert(pt.Not(v.hasValue())),
            pt.App.globalPut(key, val),
        ).__teal__(options)
    else:
        expected = pt.App.globalPut(key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.set_default().__teal__(options)
    expected_default = get_default_for_type(stack_type, default)

    if static:
        expected = pt.Seq(
            v := pt.App.globalGetEx(pt.Int(0), key),
            pt.Assert(pt.Not(v.hasValue())),
            pt.App.globalPut(key, expected_default),
        ).__teal__(options)
    else:
        expected = pt.App.globalPut(key, expected_default).__teal__(options)

    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.get().__teal__(options)
    expected = pt.App.globalGet(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.__teal__(options)
    expected = pt.App.globalGet(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe().__teal__(options)
    expected = pt.App.globalGetEx(pt.Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    if stack_type == pt.TealType.uint64 and not static:
        actual = lv.increment().__teal__(options)
        expected = pt.App.globalPut(key, pt.App.globalGet(key) + pt.Int(1)).__teal__(
            options
        )
        with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
            assert actual == expected

        actual = lv.decrement().__teal__(options)
        expected = pt.App.globalPut(key, pt.App.globalGet(key) - pt.Int(1)).__teal__(
            options
        )
        with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
            assert actual == expected

    else:
        with pytest.raises(pt.TealInputError):
            lv.increment()

        with pytest.raises(pt.TealInputError):
            lv.decrement()

    default = get_default_for_type(stack_type=stack_type, default=None)
    actual = lv.get_else(default).__teal__(options)
    expected = pt.If(
        (v := pt.App.globalGetEx(pt.Int(0), key)).hasValue(), v.value(), default
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.get_must().__teal__(options)
    expected = pt.Seq(
        (v := pt.App.globalGetEx(pt.Int(0), key)), pt.Assert(v.hasValue()), v.value()
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.delete().__teal__(options)
    expected = pt.App.globalDel(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


DYNAMIC_APPLICATION_VALUE_TESTS = [
    # stack type, max keys, key gen, key_seed, val, expected error
    (pt.TealType.uint64, 1, None, pt.Bytes("abc"), pt.Int(1), None),
    (pt.TealType.bytes, 1, None, pt.Bytes("abc"), pt.Bytes("abc"), None),
    (pt.TealType.bytes, 1, None, pt.abi.String(), pt.Bytes("abc"), None),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.bytes)(
            lambda v: pt.Substring(v, pt.Int(0), pt.Int(1))
        ),
        pt.Bytes("abc"),
        pt.Bytes("abc"),
        None,
    ),
    (
        pt.TealType.bytes,
        1,
        pt.Subroutine(pt.TealType.uint64)(lambda v: pt.Int(1)),
        pt.Bytes("abc"),
        pt.Bytes("abc"),
        pt.TealTypeError,
    ),
    (pt.TealType.uint64, 1, None, pt.Bytes("abc"), pt.Bytes("abc"), pt.TealTypeError),
    (pt.TealType.bytes, 1, None, pt.Bytes("abc"), pt.Int(1), pt.TealTypeError),
    (pt.TealType.uint64, 0, None, pt.Bytes("abc"), pt.Int(1), Exception),
    (pt.TealType.uint64, 65, None, pt.Bytes("abc"), pt.Int(1), Exception),
]


@pytest.mark.parametrize(
    "stack_type, max_keys, key_gen, key_seed, val, error",
    DYNAMIC_APPLICATION_VALUE_TESTS,
)
def test_dynamic_global_value(stack_type, max_keys, key_gen, key_seed, val, error):
    if error is not None:
        with pytest.raises(error):
            do_dynamic_gv_test(stack_type, max_keys, key_gen, key_seed, val)
    else:
        do_dynamic_gv_test(stack_type, max_keys, key_gen, key_seed, val)


def do_dynamic_gv_test(stack_type, max_keys, key_gen, key_seed, val):
    dlv = DynamicApplicationStateValue(
        stack_type=stack_type, max_keys=max_keys, key_gen=key_gen
    )

    lv = dlv[key_seed]

    key = key_seed
    if isinstance(key, pt.abi.BaseType):
        key = key.encode()

    if key_gen is not None:
        key = key_gen(key_seed)

    actual = lv.set(val).__teal__(options)
    expected = pt.App.globalPut(key, val).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get().__teal__(options)
    expected = pt.App.globalGet(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.__teal__(options)
    expected = pt.App.globalGet(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected

    actual = lv.get_maybe().__teal__(options)
    expected = pt.App.globalGetEx(pt.Int(0), key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    if stack_type == pt.TealType.uint64:
        actual = lv.increment().__teal__(options)
        expected = pt.App.globalPut(key, pt.App.globalGet(key) + pt.Int(1)).__teal__(
            options
        )
        with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
            assert actual == expected

        actual = lv.decrement().__teal__(options)
        expected = pt.App.globalPut(key, pt.App.globalGet(key) - pt.Int(1)).__teal__(
            options
        )
        with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
            assert actual == expected

    else:
        with pytest.raises(pt.TealInputError):
            lv.increment()

        with pytest.raises(pt.TealInputError):
            lv.decrement()

    default = get_default_for_type(stack_type=stack_type, default=None)
    actual = lv.get_else(default).__teal__(options)
    expected = pt.If(
        (v := pt.App.globalGetEx(pt.Int(0), key)).hasValue(), v.value(), default
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.get_must().__teal__(options)
    expected = pt.Seq(
        (v := pt.App.globalGetEx(pt.Int(0), key)), pt.Assert(v.hasValue()), v.value()
    ).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality(), pt.TealComponent.Context.ignoreScratchSlotEquality():
        assert actual == expected

    actual = lv.delete().__teal__(options)
    expected = pt.App.globalDel(key).__teal__(options)
    with pt.TealComponent.Context.ignoreExprEquality():
        assert actual == expected


def test_impl_expr():
    asv = AccountStateValue(pt.TealType.uint64)
    assert asv.has_return() is False
    assert asv.type_of() == pt.TealType.uint64

    asv = ApplicationStateValue(pt.TealType.uint64)
    assert asv.has_return() is False
    assert asv.type_of() == pt.TealType.uint64


def test_application_state():
    statevals = {
        "a": ApplicationStateValue(pt.TealType.uint64),
        "b": ApplicationStateValue(pt.TealType.bytes),
    }
    astate = ApplicationState(statevals)

    assert astate.num_byte_slices == 1
    assert astate.num_uints == 1

    statevals["c"] = DynamicApplicationStateValue(pt.TealType.uint64, max_keys=64)
    with pytest.raises(Exception):
        ApplicationState(statevals)


def test_account_state():
    statevals = {
        "a": AccountStateValue(pt.TealType.uint64),
        "b": AccountStateValue(pt.TealType.bytes),
    }
    astate = AccountState(statevals)

    assert astate.num_byte_slices == 1
    assert astate.num_uints == 1

    statevals["c"] = DynamicAccountStateValue(pt.TealType.uint64, max_keys=16)
    with pytest.raises(Exception):
        AccountState(statevals)
