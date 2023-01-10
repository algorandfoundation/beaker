from abc import abstractmethod, ABC
from copy import copy
from typing import Callable, Mapping, cast, Any, Optional
from algosdk.future.transaction import StateSchema
from pyteal import (
    abi,
    SubroutineFnWrapper,
    TealType,
    TealTypeError,
    Expr,
    CompileOptions,
    App,
    Bytes,
    Int,
    TealInputError,
    Assert,
    Not,
    MaybeValue,
    Txn,
    Seq,
    If,
    Subroutine,
    Concat,
    TealBlock,
    TealSimpleBlock,
)
from beaker.lib.storage import LocalBlob
from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.lib.storage.global_blob import GlobalBlob


def prefix_key_gen(prefix: str) -> SubroutineFnWrapper:
    @Subroutine(TealType.bytes)
    def prefix_key_gen(key_seed: Expr) -> Expr:
        return Concat(Bytes(prefix), key_seed)

    return prefix_key_gen


def identity_key_gen(key_seed: Expr) -> Expr:
    return key_seed


class StateValue(Expr):
    """Base Class for state values

    Attributes:
        stack_type: The type of the state value
            (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can
            only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: TealType,
        key: Expr | None = None,
        default: Expr | None = None,
        static: bool = False,
        descr: str | None = None,
    ):
        super().__init__()

        self.stack_type = stack_type
        self.static = static
        self.descr = descr

        if key is not None and key.type_of() != TealType.bytes:
            raise TealTypeError(key.type_of(), TealType.bytes)
        self.key = key

        if default is not None and default.type_of() != self.stack_type:
            raise TealTypeError(default.type_of(), self.stack_type)
        self.default = default

    # Required methods for `Expr subclass`
    def has_return(self) -> bool:
        return False

    def type_of(self) -> TealType:
        return self.stack_type

    def __teal__(self, options: CompileOptions) -> tuple[TealBlock, TealSimpleBlock]:
        return self.get().__teal__(options)

    def __str__(self) -> str:
        return f"StateValue {self.key}"

    def str_key(self) -> str:
        """returns the string held by the key Bytes object"""
        return cast(Bytes, self.key).byte_str.replace('"', "")

    def increment(self, cnt: Expr = Int(1)) -> Expr:
        """helper to increment a counter"""
        check_is_int(self)
        check_not_static(self)

        return self.set(self.get() + cnt)

    def decrement(self, cnt: Expr = Int(1)) -> Expr:
        """helper to decrement a counter"""
        check_is_int(self)
        check_not_static(self)

        return self.set(self.get() - cnt)

    def set_default(self) -> Expr:
        """sets the default value if one is provided, if
        none provided sets the zero value for its type"""

        return self.set(_get_default_for_type(self.stack_type, self.default))

    def is_default(self) -> Expr:
        """checks to see if the value set equals the default value"""
        default = _get_default_for_type(self.stack_type, self.default)
        return self.get() == default

    @abstractmethod
    def set(self, val: Expr) -> Expr:
        """sets the value to the argument passed"""

    @abstractmethod
    def get(self) -> Expr:
        """gets the value stored for this state value"""

    @abstractmethod
    def get_maybe(self) -> MaybeValue:
        """gets a MaybeValue that can be used for existence check"""

    @abstractmethod
    def get_must(self) -> Expr:
        """gets the value stored at the key. if none is stored, Assert out of the program"""

    @abstractmethod
    def get_else(self, val: Expr) -> Expr:
        """gets the value stored at the key. if none is stored, return the value passed"""

    @abstractmethod
    def exists(self) -> Expr:
        """checks if the value is set (to whatever value. Returns Int(1) if value is set, Int(0) otherwise."""

    @abstractmethod
    def delete(self) -> Expr:
        """deletes the key from state, if the value is static it will be a compile time error"""


class ReservedStateValue(ABC):
    """Base Class for ReservedStateValues

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (subroutine): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients

    """

    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        self.stack_type = stack_type
        self.max_keys = max_keys
        self.descr = descr
        self.key_generator: Optional[SubroutineFnWrapper | Callable] = None

        if key_gen is not None:
            self.set_key_gen(key_gen)

    def set_key_gen(self, key_gen: SubroutineFnWrapper | Callable) -> None:
        if (
            isinstance(key_gen, SubroutineFnWrapper)
            and key_gen.type_of() != TealType.bytes
        ):
            raise TealTypeError(key_gen.type_of(), TealType.bytes)
        self.key_generator = key_gen

    @abstractmethod
    def __getitem__(self, key_seed: Expr | abi.BaseType) -> StateValue:
        """Method to access the state value with the key seed provided"""


class ApplicationStateValue(StateValue):
    """Allows storage of state values for an application (global state)

    Attributes:
        stack_type: The type of the state value (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def __str__(self) -> str:
        return f"ApplicationStateValue {self.key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        if self.static:
            return Seq(
                v := App.globalGetEx(Int(0), self.key),
                Assert(Not(v.hasValue())),
                App.globalPut(self.key, val),
            )

        return App.globalPut(self.key, val)

    def get(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        return App.globalGet(self.key)

    def get_maybe(self) -> MaybeValue:
        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        return App.globalGetEx(Int(0), self.key)

    def get_must(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        return If((v := App.globalGetEx(Int(0), self.key)).hasValue(), v.value(), val)

    def get_external(self, app_id: Expr) -> MaybeValue:
        if app_id.type_of() is not TealType.uint64:
            raise TealTypeError(app_id, TealType.uint64)

        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")
        return App.globalGetEx(app_id, self.key)

    def exists(self) -> Expr:
        return Seq(val := self.get_maybe(), val.hasValue())

    def delete(self) -> Expr:
        check_not_static(self)

        if self.key is None:
            raise TealInputError(f"ApplicationStateValue {self} has no key defined")

        return App.globalDel(self.key)


class ReservedApplicationStateValue(ReservedStateValue):
    """Reserved Application State (global state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_GLOBAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_GLOBAL_STATE}")

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> ApplicationStateValue:
        """Method to access the state value with the key seed provided"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        key = cast(Expr, key)

        if self.key_generator is not None:
            key = self.key_generator(key)

        return ApplicationStateValue(
            stack_type=self.stack_type, key=key, descr=self.descr
        )


class AccountStateValue(StateValue):
    """Allows storage of keyed values for an account opted into an application (local state)

    Attributes:
        stack_type: The type of the state value (either TealType.bytes or TealType.uint64)
        key: key to use to store the the value, default is name of class variable
        default: Default value for the state value
        static: Boolean flag to denote that this state value can only be set once and not deleted.
        descr: Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: TealType,
        key: Expr | None = None,
        default: Expr | None = None,
        static: bool = False,
        descr: str | None = None,
    ):
        super().__init__(stack_type, key, default, static, descr)
        self.acct: Expr = Txn.sender()

    def __str__(self) -> str:
        return f"AccountStateValue {self.acct} {self.key}"

    def set(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        if self.static:
            return Seq(
                v := self.get_maybe(),
                Assert(Not(v.hasValue())),
                App.localPut(self.acct, self.key, val),
            )

        return App.localPut(self.acct, self.key, val)

    def get(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localGet(self.acct, self.key)

    def get_maybe(self) -> MaybeValue:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")

        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localGetEx(self.acct, Int(0), self.key)

    def get_must(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return Seq(val := self.get_maybe(), Assert(val.hasValue()), val.value())

    def get_else(self, val: Expr) -> Expr:
        check_match_type(self, val)

        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return If(
            (v := App.localGetEx(self.acct, Int(0), self.key)).hasValue(),
            v.value(),
            val,
        )

    def get_external(self, app_id: Expr) -> MaybeValue:
        if app_id.type_of() is not TealType.uint64:
            raise TealTypeError(app_id, TealType.uint64)

        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localGetEx(self.acct, app_id, self.key)

    def exists(self) -> Expr:
        return Seq(val := self.get_maybe(), val.hasValue())

    def delete(self) -> Expr:
        if self.key is None:
            raise TealInputError(f"AccountStateValue {self} has no key defined")
        if self.acct is None:
            raise TealInputError(f"AccountStateValue {self} has no account defined")

        return App.localDel(self.acct, self.key)

    def __getitem__(self, acct: Expr) -> "AccountStateValue":
        asv = copy(self)
        asv.acct = acct
        return asv


class ReservedAccountStateValue(ReservedStateValue):
    """Reserved Account State (local state)

    Used when there should be a number of reserved state fields but the keys are uncertain at build time.

    Attributes:
        stack_type (TealType): The type of the state value (either TealType.bytes or TealType.uint64)
        max_keys (int): Maximum number of keys to reserve for this reserved state value
        key_gen (SubroutineFnWrapper): A subroutine returning TealType.bytes, used to create a key where some data is stored.
        descr (str): Description of the state value to provide some information to clients
    """

    def __init__(
        self,
        stack_type: TealType,
        max_keys: int,
        key_gen: Optional[SubroutineFnWrapper | Callable] = None,
        descr: str | None = None,
    ):
        super().__init__(stack_type, max_keys, key_gen, descr)

        if max_keys <= 0 or max_keys > MAX_LOCAL_STATE:
            raise Exception(f"max keys expected to be between 0 and {MAX_LOCAL_STATE}")

    def __getitem__(self, key_seed: Expr | abi.BaseType) -> AccountStateValue:
        """Access AccountState value given key_seed"""
        key = key_seed

        if isinstance(key_seed, abi.BaseType):
            key = key_seed.encode()

        if self.key_generator is not None:
            key = self.key_generator(key)

        return AccountStateValue(stack_type=self.stack_type, key=cast(Expr, key))


class StateBlob(ABC):
    def __init__(self, num_keys: int):
        self.num_keys = num_keys

    @abstractmethod
    def initialize(self) -> Expr:
        ...

    @abstractmethod
    def read(self, start: Expr, stop: Expr) -> Expr:
        """
        Reads some bytes from the buffer

        Args:
            start: An ``Expr`` that represents the start index to read from. Should evaluate to ``uint64``.
            stop: An ``Expr`` that represents the stop index to read until. Should evaluate to ``uint64``.
        Returns:
            The bytes read from the blob from start to stop
        """
        ...

    @abstractmethod
    def write(self, start: Expr, buff: Expr) -> Expr:
        """
        Writes the buffer to the blob

        Args:
            start: An ``Expr`` that represents where to start writing. Should evaluate to ``uint64``.
            buff: An ``Expr`` that represents the bytes to write. Should evaluate to ``bytes``.

        """
        ...

    @abstractmethod
    def read_byte(self, idx: Expr) -> Expr:
        """
        Reads a single byte from the given index

        Args:
            idx: An ``Expr`` that represents the index into the blob to read the byte from. Should evaluate to ``uint64``.

        Returns:
            A single byte as a ``uint64``

        """
        ...

    @abstractmethod
    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        """
        Writes a single byte to the given index

        Args:
            idx: An ``Expr`` that represents the index to write the byte to. Should evaluate to ``uint64``.
            byte: An ``Expr`` That represents the index to write the byte to. Should evaluate to ``uint64``.

        """
        ...


class AccountStateBlob(StateBlob):
    def __init__(self, keys: Optional[int | list[int]] = None):
        self.blob = LocalBlob(keys=keys)
        self.acct: Expr = Txn.sender()

        super().__init__(self.blob._max_keys)

    def __getitem__(self, acct: Expr) -> "AccountStateBlob":
        asv = copy(self)
        asv.acct = acct
        return asv

    def initialize(self) -> Expr:
        return self.blob.zero(acct=self.acct)

    def write(self, start: Expr, buff: Expr) -> Expr:
        return self.blob.write(start, buff, acct=self.acct)

    def read(self, start: Expr, stop: Expr) -> Expr:
        return self.blob.read(start, stop, acct=self.acct)

    def read_byte(self, idx: Expr) -> Expr:
        return self.blob.get_byte(idx, acct=self.acct)

    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        return self.blob.set_byte(idx, byte, acct=self.acct)


class ApplicationStateBlob(StateBlob):
    def __init__(self, keys: Optional[int | list[int]] = None):
        self.blob = GlobalBlob(keys=keys)
        super().__init__(self.blob._max_keys)

    def initialize(self) -> Expr:
        return self.blob.zero()

    def write(self, start: Expr, buff: Expr) -> Expr:
        return self.blob.write(start, buff)

    def read(self, start: Expr, stop: Expr) -> Expr:
        return self.blob.read(start, stop)

    def read_byte(self, idx: Expr) -> Expr:
        return self.blob.get_byte(idx)

    def write_byte(self, idx: Expr, byte: Expr) -> Expr:
        return self.blob.set_byte(idx, byte)


def check_not_static(sv: StateValue) -> None:
    if sv.static:
        raise TealInputError(f"StateValue {sv} is static")


def check_is_int(sv: StateValue) -> None:
    if sv.stack_type != TealType.uint64:
        raise TealInputError(f"StateValue {sv} is not integer type")


def check_match_type(sv: StateValue, val: Expr) -> None:
    in_type = val.type_of()
    if in_type != sv.stack_type and in_type != TealType.anytype:
        raise TealTypeError(in_type, sv.stack_type)


class State:
    """holds all the declared and reserved state values for this storage type"""

    def __init__(
        self, fields: Mapping[str, StateValue | ReservedStateValue | StateBlob]
    ):
        self.declared_vals: dict[str, StateValue] = {
            k: v for k, v in fields.items() if isinstance(v, StateValue)
        }
        self.__dict__.update(self.declared_vals)

        self.blob_vals: dict[str, StateBlob] = {
            k: v for k, v in fields.items() if isinstance(v, StateBlob)
        }
        self.__dict__.update(self.blob_vals)

        self.reserved_vals: dict[str, ReservedStateValue] = {
            k: v for k, v in fields.items() if isinstance(v, ReservedStateValue)
        }
        self.__dict__.update(self.reserved_vals)

        self.num_uints = len(
            [l for l in self.declared_vals.values() if l.stack_type == TealType.uint64]
        ) + sum(
            [
                l.max_keys
                for l in self.reserved_vals.values()
                if l.stack_type == TealType.uint64
            ]
        )

        self.num_byte_slices = (
            len(
                [
                    l
                    for l in self.declared_vals.values()
                    if l.stack_type == TealType.bytes
                ]
            )
            + sum(
                [
                    l.max_keys
                    for l in self.reserved_vals.values()
                    if l.stack_type == TealType.bytes
                ]
            )
            + sum([b.num_keys for b in self.blob_vals.values()])
        )

    def dictify(self) -> dict[str, dict[str, Any]]:
        """Convert the state to a dict for encoding"""
        return {
            "declared": {
                k: {
                    "type": _stack_type_to_string(v.stack_type),
                    "key": v.str_key(),
                    "descr": v.descr if v.descr is not None else "",
                }
                for k, v in self.declared_vals.items()
            },
            "reserved": {
                k: {
                    "type": _stack_type_to_string(v.stack_type),
                    "max_keys": v.max_keys,
                    "descr": v.descr if v.descr is not None else "",
                }
                for k, v in self.reserved_vals.items()
            },
        }

    def schema(self) -> StateSchema:
        """gets the schema as num uints/bytes for app create transactions"""
        return StateSchema(
            num_uints=self.num_uints, num_byte_slices=self.num_byte_slices
        )


class ApplicationState(State):
    def __init__(
        self,
        fields: Mapping[
            str,
            ApplicationStateValue
            | ReservedApplicationStateValue
            | ApplicationStateBlob,
        ],
    ):
        super().__init__(fields)
        if (total := self.num_uints + self.num_byte_slices) > MAX_GLOBAL_STATE:
            raise Exception(
                f"Too much application state, expected {total} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                v.set_default()
                for v in self.declared_vals.values()
                if not v.static or (v.static and v.default is not None)
            ]
            + [v.initialize() for v in self.blob_vals.values()]
        )


class AccountState(State):
    def __init__(
        self,
        fields: Mapping[
            str, AccountStateValue | ReservedAccountStateValue | AccountStateBlob
        ],
    ):
        super().__init__(fields)
        if (total := self.num_uints + self.num_byte_slices) > MAX_LOCAL_STATE:
            raise Exception(
                f"Too much account state, expected {total} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *[
                cast(AccountStateValue, v)[acct].set_default()
                for v in self.declared_vals.values()
                if not v.static or (v.static and v.default is not None)
            ]
            + [v.initialize() for v in self.blob_vals.values()]
        )


def _get_default_for_type(stack_type: TealType, default: Expr | None) -> Expr:
    if default is not None:
        return default

    if stack_type == TealType.bytes:
        return Bytes("")
    else:
        return Int(0)


def _stack_type_to_string(st: TealType) -> str:
    if st == TealType.uint64:
        return "uint64"
    if st == TealType.bytes:
        return "bytes"
    else:
        raise Exception("Only uint64 and bytes supported")
