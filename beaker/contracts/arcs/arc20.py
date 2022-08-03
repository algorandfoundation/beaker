from typing import Final
from pyteal import (
    abi,
    Int,
    Len,
    TealType,
    Global,
    Bytes,
    Concat,
    Seq,
    Assert,
    And,
    Txn,
    Not,
    MethodConfig,
    AssetParam,
    AssetHolding,
    If,
    Expr,
    CallConfig,
    Gtxn,
    TxnType,
    Or,
    TxnField,
    InnerTxnBuilder,
    Reject,
    InnerTxn,
)
from beaker import (
    internal,
    external,
    Application,
    ApplicationStateValue,
    AccountStateValue,
    Authorize,
    opt_in,
)
from beaker.lib.strings import itoa


# NOTE: The following costs could change over time with protocol upgrades.
OPTIN_COST = 100_000
UINTS_COST = 28_500
BYTES_COST = 50_000


# MetadataHash = abi.StaticArray[abi.Byte, Literal[32]]
#: Alias for arbitrary byte array
MetadataHash = abi.DynamicArray[abi.Byte]

# Inline Validators
def valid_address_length(addr: Expr) -> Expr:
    return Len(addr) == Int(32)


def valid_url_length(url: Expr) -> Expr:
    # return Len(url) <= Int(96)
    return Int(1)


def valid_name_length(name: Expr) -> Expr:
    # return Len(name) <= Int(32)
    return Int(1)


def valid_unit_name_length(unit_name: Expr) -> Expr:
    # return Len(unit_name) <= Int(8)
    return Int(1)


# Contract Implemtation
class ARC20(Application):
    """An implementation of the ARC20 interface"""

    #: The total number of units
    total: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    #: The number of decimals for display purposes
    decimals: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    #: Whether or not to freeze the asset by default
    default_frozen: Final[ApplicationStateValue] = ApplicationStateValue(
        TealType.uint64
    )
    #: The underlying asset id
    asa_id: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    #: Whether or not this asset is currently frozen
    frozen: Final[ApplicationStateValue] = ApplicationStateValue(TealType.uint64)
    #: The short name of this asset
    unit_name: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    #: The longer name of this asset
    name: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    #: The url for the asset where one might find additional data
    url: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    #: The hash of the asset metadata
    metadata_hash: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes)
    #: The address that may make changes to the configuration of the asset
    manager_addr: Final[ApplicationStateValue] = ApplicationStateValue(
        TealType.bytes, default=Global.zero_address()
    )
    #: The address that holds any un-minted assets
    reserve_addr: Final[ApplicationStateValue] = ApplicationStateValue(
        TealType.bytes, default=Global.zero_address()
    )
    #: The address that may issue freeze/unfreeze transactions
    freeze_addr: Final[ApplicationStateValue] = ApplicationStateValue(
        TealType.bytes, default=Global.zero_address()
    )
    #: The address that may issue clawback transactions
    clawback_addr: Final[ApplicationStateValue] = ApplicationStateValue(
        TealType.bytes, default=Global.zero_address()
    )

    #: The id of the asset this account holds, necessary in case the asset id changes in the global config
    current_asa_id: Final[AccountStateValue] = AccountStateValue(
        TealType.uint64, default=asa_id
    )
    #: Whether or not this asset is frozen for this account
    is_frozen: Final[AccountStateValue] = AccountStateValue(TealType.uint64)

    ########
    # Class vars that may be overridden
    ########

    SMART_ASA_APP_BINDING = "smart-asa-app-id:"

    UNDERLYING_ASA_TOTAL = Int(2**64 - 1)
    UNDERLYING_ASA_DECIMALS = Int(0)
    UNDERLYING_ASA_DEFAULT_FROZEN = Int(1)
    UNDERLYING_ASA_UNIT_NAME = Bytes("S-ASA")
    UNDERLYING_ASA_NAME = Bytes("SMART-ASA")
    UNDERLYING_ASA_URL = Concat(
        Bytes(SMART_ASA_APP_BINDING), itoa(Global.current_application_id())
    )
    UNDERLYING_ASA_METADATA_HASH = Bytes("")
    UNDERLYING_ASA_MANAGER_ADDR = Global.current_application_address()
    UNDERLYING_ASA_RESERVE_ADDR = Global.current_application_address()
    UNDERLYING_ASA_FREEZE_ADDR = Global.current_application_address()
    UNDERLYING_ASA_CLAWBACK_ADDR = Global.current_application_address()

    #######
    # ABI Handlers
    #######

    @external(authorize=Authorize.only(Global.creator_address()))
    def asset_create(
        self,
        total: abi.Uint64,
        decimals: abi.Uint32,
        default_frozen: abi.Bool,
        unit_name: abi.String,
        name: abi.String,
        url: abi.String,
        metadata_hash: MetadataHash,
        manager_addr: abi.Address,
        reserve_addr: abi.Address,
        freeze_addr: abi.Address,
        clawback_addr: abi.Address,
        *,
        output: abi.Uint64,
    ):
        """creates a new asset with the config passed and sets the global parameters"""
        return Seq(
            # Preconditions
            Assert(
                # Asset not yet created
                self.asa_id.is_default(),
                # Addresses well formed
                valid_address_length(manager_addr.get()),
                valid_address_length(reserve_addr.get()),
                valid_address_length(freeze_addr.get()),
                valid_address_length(clawback_addr.get()),
                # protocol length limits
                valid_url_length(url.get()),
                valid_name_length(name.get()),
                valid_unit_name_length(unit_name.get()),
            ),
            # Effects
            # Smart ASA properties
            self.total.set(total.get()),
            self.decimals.set(decimals.get()),
            self.default_frozen.set(default_frozen.get()),
            self.unit_name.set(unit_name.get()),
            self.name.set(name.get()),
            self.url.set(url.get()),
            self.metadata_hash.set(metadata_hash.encode()),
            self.manager_addr.set(manager_addr.get()),
            self.reserve_addr.set(reserve_addr.get()),
            self.freeze_addr.set(freeze_addr.get()),
            self.clawback_addr.set(clawback_addr.get()),
            # Underlying ASA creation
            self.asa_id.set(self.do_create_asa()),
            # Return the asset id we just created
            output.set(self.asa_id),
        )

    @external(authorize=Authorize.only(manager_addr))
    def asset_config(
        self,
        config_asset: abi.Asset,
        total: abi.Uint64,
        decimals: abi.Uint32,
        default_frozen: abi.Bool,
        unit_name: abi.String,
        name: abi.String,
        url: abi.String,
        metadata_hash: MetadataHash,
        manager_addr: abi.Address,
        reserve_addr: abi.Address,
        freeze_addr: abi.Address,
        clawback_addr: abi.Address,
    ) -> Expr:
        """configures the asset in global state and possibly on the ASA itself"""

        update_reserve_addr = reserve_addr.get() != self.reserve_addr
        update_freeze_addr = freeze_addr.get() != self.freeze_addr
        update_clawback_addr = clawback_addr.get() != self.clawback_addr

        # NOTE: In ref. implementation Smart ASA total can not be configured to
        # less than its current circulating supply.
        is_valid_total = total.get() >= self.compute_circulating_supply()

        return Seq(
            # Preconditions
            Assert(
                self.asa_id == config_asset.asset_id(),
                is_valid_total,
                valid_address_length(manager_addr.get()),
                valid_address_length(reserve_addr.get()),
                valid_address_length(freeze_addr.get()),
                valid_address_length(clawback_addr.get()),
                valid_url_length(url.get()),
                valid_name_length(name.get()),
                valid_unit_name_length(unit_name.get()),
                # TODO: more checks for total/decimals
            ),
            If(update_reserve_addr).Then(
                Assert(self.reserve_addr != Global.zero_address())
            ),
            If(update_freeze_addr).Then(
                Assert(self.freeze_addr != Global.zero_address())
            ),
            If(update_clawback_addr).Then(
                Assert(self.clawback_addr != Global.zero_address())
            ),
            # Effects
            self.total.set(total.get()),
            self.decimals.set(decimals.get()),
            self.default_frozen.set(default_frozen.get()),
            self.unit_name.set(unit_name.get()),
            self.name.set(name.get()),
            self.url.set(url.get()),
            self.metadata_hash.set(metadata_hash.encode()),
            self.manager_addr.set(manager_addr.get()),
            self.reserve_addr.set(reserve_addr.get()),
            self.freeze_addr.set(freeze_addr.get()),
            self.clawback_addr.set(clawback_addr.get()),
        )

    @external
    def asset_transfer(
        self,
        xfer_asset: abi.Asset,
        asset_amount: abi.Uint64,
        asset_sender: abi.Account,
        asset_receiver: abi.Account,
    ):
        """transfers the asset from asset_sender to asset_receiver"""

        is_not_clawback = And(
            Txn.sender() == asset_sender.address(),
            Txn.sender() != self.clawback_addr,
        )

        # NOTE: Ref. implementation grants _minting_ permission to `reserve_addr`,
        # has restriction no restriction on who is the minting _receiver_.
        # WARNING: Setting Smart ASA `reserve` to ZERO_ADDRESS switches-off minting.
        is_minting = And(
            Txn.sender() == self.reserve_addr,
            Global.current_application_address() == asset_sender.address(),
        )

        # NOTE: Ref. implementation grants _burning_ permission to `reserve_addr`,
        # has restriction both on burning _sender_ and _receiver_ to prevent
        # _clawback_ through burning.
        # WARNING: Setting Smart ASA `reserve` to ZERO_ADDRESS switches-off burning.
        is_burning = And(
            Txn.sender() == self.reserve_addr,
            self.reserve_addr == asset_sender.address(),
            Global.current_application_address() == asset_receiver.address(),
        )

        is_clawback = Txn.sender() == self.clawback_addr

        # NOTE: Ref. implementation checks that `smart_asa_id` is correct in Local
        # State since the App could generate a new Smart ASA (if the previous one
        # has been destroyed) requiring users to opt-in again to gain a coherent
        # new `frozen` status.

        sender_asset_match = self.asa_id == self.current_asa_id[asset_sender.address()]
        receiver_asset_match = (
            self.asa_id == self.current_asa_id[asset_receiver.address()]
        )
        is_current_smart_asa_id = And(sender_asset_match, receiver_asset_match)

        asset_frozen = self.frozen
        asset_sender_frozen = self.is_frozen[asset_sender.address()]
        asset_receiver_frozen = self.is_frozen[asset_receiver.address()]

        return Seq(
            # Preconditions
            Assert(
                self.asa_id == xfer_asset.asset_id(),
                valid_address_length(asset_sender.address()),
                valid_address_length(asset_receiver.address()),
            ),
            If(is_not_clawback)
            .Then(
                # Asset Regular Transfer Preconditions
                Assert(
                    Not(asset_frozen),
                    Not(asset_sender_frozen),
                    Not(asset_receiver_frozen),
                    is_current_smart_asa_id,
                ),
            )
            .ElseIf(is_minting)
            .Then(
                # Asset Minting Preconditions
                Assert(
                    Not(asset_frozen),
                    Not(asset_receiver_frozen),
                    receiver_asset_match,
                    self.compute_circulating_supply() + asset_amount.get()
                    <= self.total,
                ),
            )
            .ElseIf(is_burning)
            .Then(
                Assert(
                    Not(asset_frozen),
                    Not(asset_sender_frozen),
                    sender_asset_match,
                ),
            )
            .Else(
                Assert(is_clawback),
                Assert(is_current_smart_asa_id),
            ),
            # Effects
            self.do_transfer(
                self.asa_id,
                asset_amount.get(),
                asset_sender.address(),
                asset_receiver.address(),
            ),
        )

    @external
    def asset_freeze(
        self,
        freeze_asset: abi.Asset,
        asset_frozen: abi.Bool,
    ):
        """freezes the asset globally"""
        is_correct_smart_asa_id = self.asa_id == freeze_asset.asset_id()
        is_freeze_addr = Txn.sender() == self.freeze_addr
        return Seq(
            # Asset Freeze Preconditions
            Assert(
                self.asa_id,
                is_correct_smart_asa_id,
                is_freeze_addr,
            ),
            # Effects
            self.frozen.set(asset_frozen.get()),
        )

    @external
    def account_freeze(
        self,
        freeze_asset: abi.Asset,
        freeze_account: abi.Account,
        asset_frozen: abi.Bool,
    ):
        """freezes the asset for a given account"""
        is_correct_smart_asa_id = self.asa_id == freeze_asset.asset_id()
        is_freeze_addr = Txn.sender() == self.freeze_addr
        return Seq(
            # Account Freeze Preconditions
            Assert(
                self.asa_id,
                is_correct_smart_asa_id,
                is_freeze_addr,
                valid_address_length(freeze_account.address()),
            ),
            # Effects
            self.is_frozen[freeze_account.address()].set(asset_frozen.get()),
        )

    @external
    def asset_destroy(
        self,
        destroy_asset: abi.Asset,
    ):
        """destroys the underlying ASA"""
        is_correct_smart_asa_id = self.asa_id == destroy_asset.asset_id()
        is_manager_addr = Txn.sender() == self.manager_addr
        return Seq(
            # Asset Destroy Preconditions
            Assert(
                self.asa_id,
                is_correct_smart_asa_id,
                is_manager_addr,
            ),
            # Effects
            self.do_destroy(self.asa_id),
            # Reinit state to wipe it
            self.app_state.initialize(),
        )

    @external(method_config=MethodConfig(opt_in=CallConfig.CALL))
    def asset_app_optin(
        self, asset: abi.Asset, opt_in_txn: abi.AssetTransferTransaction
    ):
        return Seq(
            # Preconditions
            account_balance := AssetHolding().balance(Txn.sender(), asset.asset_id()),
            Assert(
                self.asa_id,
                self.asa_id == asset.asset_id(),
                opt_in_txn.get().type_enum() == TxnType.AssetTransfer,
                opt_in_txn.get().xfer_asset() == self.asa_id,
                opt_in_txn.get().sender() == Txn.sender(),
                opt_in_txn.get().asset_receiver() == Txn.sender(),
                opt_in_txn.get().asset_amount() == Int(0),
                opt_in_txn.get().asset_close_to() == Global.zero_address(),
                # Make sure they actually opted in
                account_balance.hasValue(),
            ),
            self.acct_state.initialize(),
            # Effects
            If(Or(self.default_frozen, account_balance.value() > Int(0))).Then(
                self.is_frozen[Txn.sender()].set(Int(1))
            ),
        )

    @external(method_config=MethodConfig(close_out=CallConfig.CALL))
    def asset_app_closeout(self, close_asset: abi.Asset, close_to: abi.Account) -> Expr:
        close_out_txn = Gtxn[1]
        return Seq(
            Assert(
                valid_address_length(close_to.address()),
                self.current_asa_id[Txn.sender()] == close_asset.asset_id(),
                Global.group_size() >= Int(2),
                close_out_txn.type_enum() == TxnType.AssetTransfer,
                close_out_txn.xfer_asset() == close_asset.asset_id(),
                close_out_txn.sender() == Txn.sender(),
                close_out_txn.asset_amount() == Int(0),
                close_out_txn.asset_close_to() == self.address,
            ),
            # Effects
            asset_creator := AssetParam().creator(close_asset.asset_id()),
            # NOTE: If Smart ASA has been destroyed:
            #   1. The close-to address could be anyone (no check needed)
            #   2. No InnerTxn happens
            If(asset_creator.hasValue()).Then(
                # NOTE: Smart ASA has not been destroyed.
                Assert(self.asa_id == close_asset.asset_id()),
                If(Or(self.frozen, self.is_frozen[Txn.sender()])).Then(
                    # NOTE: If Smart ASA is frozen, users can only close-out to
                    # Creator
                    Assert(close_to.address() == self.address)
                ),
                If(close_to.address() != self.address).Then(
                    # NOTE: If the target of close-out is not Creator, it MUST
                    # be opted-in to the current Smart ASA.
                    Assert(
                        self.current_asa_id[close_to.address()]
                        == close_asset.asset_id()
                    )
                ),
                account_balance := AssetHolding().balance(
                    Txn.sender(), close_asset.asset_id()
                ),
                self.do_transfer(
                    close_asset.asset_id(),
                    account_balance.value(),
                    Txn.sender(),
                    close_to.address(),
                ),
            ),
        )

    @external(read_only=True)
    def get_circulating_supply(self, asset: abi.Asset, *, output: abi.Uint64):
        return Seq(
            Assert(asset.asset_id() == self.asa_id),
            output.set(self.compute_circulating_supply()),
        )

    @external(read_only=True)
    def get_total(self, asset: abi.Asset, *, output: abi.Uint64):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.total))

    @external(read_only=True)
    def get_decimals(self, asset: abi.Asset, *, output: abi.Uint64):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.decimals))

    @external(read_only=True)
    def get_default_frozen(self, asset: abi.Asset, *, output: abi.Bool):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.set(self.default_frozen)
        )

    @external(read_only=True)
    def is_asset_frozen(self, asset: abi.Asset, *, output: abi.Bool):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.frozen))

    @external(read_only=True)
    def get_unit_name(self, asset: abi.Asset, *, output: abi.String):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.unit_name))

    @external(read_only=True)
    def get_name(self, asset: abi.Asset, *, output: abi.String):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.name))

    @external(read_only=True)
    def get_url(self, asset: abi.Asset, *, output: abi.String):
        return Seq(Assert(asset.asset_id() == self.asa_id), output.set(self.url))

    @external(read_only=True)
    def get_metadata_hash(self, asset: abi.Asset, *, output: MetadataHash):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.decode(self.metadata_hash)
        )

    @external(read_only=True)
    def get_manager_addr(self, asset: abi.Asset, *, output: abi.Address):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.set(self.manager_addr)
        )

    @external(read_only=True)
    def get_reserve_addr(self, asset: abi.Asset, *, output: abi.Address):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.set(self.reserve_addr)
        )

    @external(read_only=True)
    def get_freeze_addr(self, asset: abi.Asset, *, output: abi.Address):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.set(self.freeze_addr)
        )

    @external(read_only=True)
    def get_clawback_addr(self, asset: abi.Asset, *, output: abi.Address):
        return Seq(
            Assert(asset.asset_id() == self.asa_id), output.set(self.clawback_addr)
        )

    @external(read_only=True)
    def is_account_frozen(
        self, asset: abi.Asset, acct: abi.Account, *, output: abi.Bool
    ):
        return Seq(
            Assert(
                asset.asset_id() == self.asa_id,
                self.current_asa_id[acct.address()] == asset.asset_id(),
            ),
            output.set(self.is_frozen[acct.address()]),
        )

    @internal(TealType.uint64)
    def compute_circulating_supply(self):
        smart_asa_reserve = AssetHolding.balance(
            Global.current_application_address(), self.asa_id
        )
        return Seq(
            smart_asa_reserve, self.UNDERLYING_ASA_TOTAL - smart_asa_reserve.value()
        )

    @internal(TealType.uint64)
    def do_create_asa(self) -> Expr:
        return Seq(
            InnerTxnBuilder.Execute(
                {
                    TxnField.fee: Int(0),
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_total: self.UNDERLYING_ASA_TOTAL,
                    TxnField.config_asset_decimals: self.UNDERLYING_ASA_DECIMALS,
                    TxnField.config_asset_default_frozen: self.UNDERLYING_ASA_DEFAULT_FROZEN,
                    TxnField.config_asset_unit_name: self.UNDERLYING_ASA_UNIT_NAME,
                    TxnField.config_asset_name: self.UNDERLYING_ASA_NAME,
                    TxnField.config_asset_url: self.UNDERLYING_ASA_URL,
                    TxnField.config_asset_manager: self.UNDERLYING_ASA_MANAGER_ADDR,
                    TxnField.config_asset_reserve: self.UNDERLYING_ASA_RESERVE_ADDR,
                    TxnField.config_asset_freeze: self.UNDERLYING_ASA_FREEZE_ADDR,
                    TxnField.config_asset_clawback: self.UNDERLYING_ASA_CLAWBACK_ADDR,
                }
            ),
            InnerTxn.created_asset_id(),
        )

    @internal(TealType.none)
    def do_transfer(
        self,
        asset_id: Expr,
        asset_amount: Expr,
        asset_sender: Expr,
        asset_receiver: Expr,
    ) -> Expr:
        return InnerTxnBuilder.Execute(
            {
                TxnField.fee: Int(0),
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: asset_id,
                TxnField.asset_amount: asset_amount,
                TxnField.asset_sender: asset_sender,
                TxnField.asset_receiver: asset_receiver,
            }
        )

    @internal(TealType.none)
    def do_destroy(self, asset_id: Expr):
        return InnerTxnBuilder.Execute(
            {
                TxnField.fee: Int(0),
                TxnField.type_enum: TxnType.AssetConfig,
                TxnField.config_asset: asset_id,
            }
        )

    @opt_in
    def opt_in(self) -> Expr:
        return Reject()
