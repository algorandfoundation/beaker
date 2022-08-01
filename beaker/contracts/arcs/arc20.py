from typing import Literal
from pyteal import *
from beaker import *


class ARC20(Application):
    @external
    def asset_create(
        self,
        total: abi.Uint64,
        decimals: abi.Uint32,
        default_frozen: abi.Bool,
        unit_name: abi.String,
        name: abi.String,
        url: abi.String,
        metadata_hash: abi.StaticArray[abi.Byte, Literal[32]],
        manager_addr: abi.Address,
        reserve_addr: abi.Address,
        freeze_addr: abi.Address,
        clawback_addr: abi.Address,
        *,
        output: abi.Uint64
    ):
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
        metadata_hash: abi.StaticArray[abi.Byte, Literal[32]],
        manager_addr: abi.Address,
        reserve_addr: abi.Address,
        freeze_addr: abi.Address,
        clawback_addr: abi.Address,
    ):
        pass

    @external
    def asset_transfer(
        self,
        xfer_asset: abi.Asset,
        asset_amount: abi.Uint64,
        asset_sender: abi.Account,
        asset_receiver: abi.Account
    ):
        pass

    @external
    def asset_transfer(
        self,
        freeze_asset: abi.Asset,
        asset_frozen: abi.Bool,
    ):
        pass

    @external
    def account_freeze(
        self,
        freeze_asset: abi.Asset,
        freeze_account: abi.Account,
        asset_frozen: abi.Bool,
    ):
        pass

    @external
    def account_destroy(
        self,
        destroy_asset: abi.Asset,
    ):
        pass

    @external
    def circulating_supply(
        self,
        asset: abi.Asset,
        *,
        output: abi.Uint64
    ):
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
    def get_metadata_hash(self, asset: abi.Asset, *, output: abi.StaticArray[abi.Byte, Literal[32]]):
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
