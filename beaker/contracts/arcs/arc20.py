from typing import Literal, Final
from pyteal import *
from beaker import *


# MetadataHash = abi.StaticArray[abi.Byte, Literal[32]]
MetadataHash = abi.DynamicArray[abi.Byte]


class ARC20(Application):
    """ An implementation of the ARC20 interface """

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
    manager_addr: Final[ApplicationStateValue]  = ApplicationStateValue(TealType.bytes, default=Global.zero_address())
    #: The address that holds any un-minted assets
    reserve_addr: Final[ApplicationStateValue]  = ApplicationStateValue(TealType.bytes, default=Global.zero_address())
    #: The address that may issue freeze/unfreeze transactions
    freeze_addr: Final[ApplicationStateValue]   = ApplicationStateValue(TealType.bytes, default=Global.zero_address())
    #: The address that may issue clawback transactions
    clawback_addr: Final[ApplicationStateValue] = ApplicationStateValue(TealType.bytes, default=Global.zero_address())

    #: The id of the asset this account holds, necessary in case the asset id changes in the global config
    current_asa_id: Final[AccountStateValue] = AccountStateValue(TealType.uint64, default=asa_id)
    #: Whether or not this asset is frozen for this account
    is_frozen: Final[AccountStateValue] = AccountStateValue(TealType.uint64)


    @external
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
        output: abi.Uint64
    ):
        """creates a new asset with the config passed and sets the global parameters"""

        pass

    @external
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
    ):
        """configures the asset in global state and possibly on the ASA itself"""
        pass

    @external
    def asset_transfer(
        self,
        xfer_asset: abi.Asset,
        asset_amount: abi.Uint64,
        asset_sender: abi.Account,
        asset_receiver: abi.Account,
    ):
        """ transfers the asset from asset_sender to asset_receiver """
        pass

    @external
    def asset_freeze(
        self,
        freeze_asset: abi.Asset,
        asset_frozen: abi.Bool,
    ):
        """freezes the asset globally"""
        pass

    @external
    def account_freeze(
        self,
        freeze_asset: abi.Asset,
        freeze_account: abi.Account,
        asset_frozen: abi.Bool,
    ):
        """freezes the asset for a given account"""
        pass

    @external
    def account_destroy(
        self,
        destroy_asset: abi.Asset,
    ):
        """destroys the underlying ASA"""
        pass

    @external(read_only=True)
    def get_circulating_supply(self, asset: abi.Asset, *, output: abi.Uint64):
        pass

    @external(read_only=True)
    def get_total(self, asset: abi.Asset, *, output: abi.Uint64):
        pass

    @external(read_only=True)
    def get_decimals(self, asset: abi.Asset, *, output: abi.Uint64):
        pass

    @external(read_only=True)
    def get_decimals(self, asset: abi.Asset, *, output: abi.Uint64):
        pass

    @external(read_only=True)
    def get_default_frozen(self, asset: abi.Asset, *, output: abi.Bool):
        pass

    @external(read_only=True)
    def get_default_frozen(self, asset: abi.Asset, *, output: abi.Uint64):
        pass

    @external(read_only=True)
    def get_unit_name(self, asset: abi.Asset, *, output: abi.String):
        pass

    @external(read_only=True)
    def get_name(self, asset: abi.Asset, *, output: abi.String):
        pass

    @external(read_only=True)
    def get_name(self, asset: abi.Asset, *, output: abi.String):
        pass

    @external(read_only=True)
    def get_url(self, asset: abi.Asset, *, output: abi.String):
        pass

    @external(read_only=True)
    def get_metadata_hash(self, asset: abi.Asset, *, output: abi.String):
        pass

    @external(read_only=True)
    def get_metadata_hash(self, asset: abi.Asset, *, output: MetadataHash):
        pass

    @external(read_only=True)
    def get_manager_addr(self, asset: abi.Asset, *, output: abi.Address):
        pass

    @external(read_only=True)
    def get_reserve_addr(self, asset: abi.Asset, *, output: abi.Address):
        pass

    @external(read_only=True)
    def get_freeze_addr(self, asset: abi.Asset, *, output: abi.Address):
        pass

    @external(read_only=True)
    def get_freeze_addr(self, asset: abi.Asset, *, output: abi.Address):
        pass

    @external(read_only=True)
    def get_clawback_addr(self, asset: abi.Asset, *, output: abi.Address):
        pass
