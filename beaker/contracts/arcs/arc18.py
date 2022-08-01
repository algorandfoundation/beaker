from typing import Final
from pyteal import (
    abi,
    TealType,
    Subroutine,
    Itob,
    Assert,
    Global,
    Bytes,
    Int,
    Seq,
    AssetHolding,
    AssetParam,
    Txn,
    If,
    And,
    InnerTxnBuilder,
    ScratchVar,
    TxnField,
    TxnType,
    Not,
    ExtractUint64,
    Extract,
    WideRatio,
    Concat,
)

from beaker import Application, ApplicationStateValue, DynamicAccountStateValue
from beaker.decorators import Authorize, external, create, update, delete


class ARC18(Application):

    administrator: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, key=Bytes("admin"), default=Global.creator_address()
    )
    royalty_basis: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64, key=Bytes("royalty_basis"), static=True
    )
    royalty_receiver: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, key=Bytes("royalty_receiver"), static=True
    )

    offers: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=16,
        key_gen=Subroutine(TealType.bytes)(lambda asset_id: Itob(asset_id)),
    )

    # A basis point is 1/100 of 1%
    basis_point_multiplier: Final[Int] = Int(100 * 100)

    ###
    # App Lifecycle
    ###

    @create
    def create(self):
        return self.initialize_application_state()

    @update
    def update(self):
        return Assert(Txn.sender() == ARC18.administrator)

    @delete
    def delete(self):
        return Assert(Txn.sender() == ARC18.administrator)

    ###
    # Admin
    ###

    @external(authorize=Authorize.only(administrator))
    def set_administrator(self, new_admin: abi.Address):
        """Sets the administrator for this royalty enforcer"""
        return self.administrator.set(new_admin.get())

    @external(authorize=Authorize.only(administrator))
    def set_policy(self, royalty_basis: abi.Uint64, royalty_receiver: abi.Address):
        """Sets the royalty basis and royalty receiver for this royalty enforcer"""
        return Seq(
            Assert(royalty_basis.get() <= self.basis_point_multiplier),
            self.royalty_basis.set(royalty_basis.get()),
            self.royalty_receiver.set(royalty_receiver.get()),
        )

    @external(authorize=Authorize.only(administrator))
    def set_payment_asset(self, payment_asset: abi.Asset, is_allowed: abi.Bool):
        """Triggers the contract account to opt in or out of an asset that may be used for payment of royalties"""
        return Seq(
            bal := AssetHolding.balance(
                Global.current_application_address(), payment_asset.asset_id()
            ),
            creator := AssetParam.creator(payment_asset.asset_id()),
            If(And(is_allowed.get(), Not(bal.hasValue())))
            .Then(
                # Opt in to asset
                Seq(
                    InnerTxnBuilder.Begin(),
                    InnerTxnBuilder.SetFields(
                        {
                            TxnField.type_enum: TxnType.AssetTransfer,
                            TxnField.xfer_asset: payment_asset.asset_id(),
                            TxnField.asset_amount: Int(0),
                            TxnField.asset_receiver: Global.current_application_address(),
                        }
                    ),
                    InnerTxnBuilder.Submit(),
                ),
            )
            .ElseIf(And(Not(is_allowed.get()), bal.hasValue()))
            .Then(
                # Opt out, close asset to asset creator
                Seq(
                    InnerTxnBuilder.Begin(),
                    InnerTxnBuilder.SetFields(
                        {
                            TxnField.type_enum: TxnType.AssetTransfer,
                            TxnField.xfer_asset: payment_asset.asset_id(),
                            TxnField.asset_amount: Int(0),
                            TxnField.asset_close_to: creator.value(),
                            TxnField.asset_receiver: creator.value(),
                        }
                    ),
                    InnerTxnBuilder.Submit(),
                ),
            ),
        )

    @external
    def transfer_algo_payment(
        self,
        royalty_asset: abi.Asset,
        royalty_asset_amount: abi.Uint64,
        owner: abi.Account,
        buyer: abi.Account,
        royalty_receiver: abi.Account,
        payment_txn: abi.PaymentTransaction,
        offered_amt: abi.Uint64,
    ):
        """Transfers an Asset from one account to another and enforces royalty payments.
        This instance of the `transfer` method requires a PaymentTransaction for payment in algos
        """

        # Get the auth_addr from local state of the owner
        # If its not present, a 0 is returned and the call fails when we try
        # to compare to the bytes of Txn.sender
        offer_amt = ScratchVar(TealType.uint64)
        offer_auth_addr = ScratchVar(TealType.bytes)

        valid_transfer_group = Seq(
            Assert(Global.group_size() == Int(2)),
            (offer := ScratchVar()).store(
                self.offers[royalty_asset.asset_id()][owner.address()]
            ),
            offer_auth_addr.store(self.offered_auth(offer.load())),
            offer_amt.store(self.offered_amount(offer.load())),
            # App call sent by authorizing address
            Assert(Txn.sender() == offer_auth_addr.load()),
            # payment txn should also be from auth address
            Assert(payment_txn.get().sender() == offer_auth_addr.load()),
            # transfer amount <= offered amount
            Assert(royalty_asset_amount.get() <= offer_amt.load()),
            # Make sure payments are going to the right participants
            Assert(payment_txn.get().receiver() == Application.address),
            Assert(royalty_receiver.address() == self.royalty_receiver),
        )

        return Seq(
            # Make sure transactions look right
            valid_transfer_group,
            # Make royalty payment
            ARC18.do_pay_algos(
                payment_txn.get().amount(),
                owner.address(),
                royalty_receiver.address(),
                self.royalty_basis,
            ),
            # Perform asset move
            ARC18.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                buyer.address(),
                royalty_asset_amount.get(),
            ),
            # Clear listing from local state of owner
            ARC18.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                offer_auth_addr.load(),
                offer_amt.load() - royalty_asset_amount.get(),
                Txn.sender(),
                offered_amt.get(),
            ),
        )

    @external
    def transfer_asset_payment(
        self,
        royalty_asset: abi.Asset,
        royalty_asset_amount: abi.Uint64,
        owner: abi.Account,
        buyer: abi.Account,
        royalty_receiver: abi.Account,
        payment_txn: abi.AssetTransferTransaction,
        payment_asset: abi.Asset,
        offered_amt: abi.Uint64,
    ):
        """Transfers an Asset from one account to another and enforces royalty payments.
        This instance of the `transfer` method requires an AssetTransfer transaction and an Asset to be passed
        corresponding to the Asset id of the transfer transaction."""

        # Get the auth_addr from local state of the owner
        # If its not present, a 0 is returned and the call fails when we try
        # to compare to the bytes of Txn.sender
        offer_amt = ScratchVar(TealType.uint64)
        offer_auth_addr = ScratchVar(TealType.bytes)

        valid_transfer_group = Seq(
            Assert(Global.group_size() == Int(2)),
            # Get the offer from local state
            (offer := ScratchVar()).store(
                self.offers[royalty_asset.asset_id()][owner.address()].get_must()
            ),
            offer_auth_addr.store(ARC18.offered_auth(offer.load())),
            offer_amt.store(ARC18.offered_amount(offer.load())),
            # App call sent by authorizing address
            Assert(Txn.sender() == offer_auth_addr.load()),
            # payment txn should be from auth
            Assert(payment_txn.get().sender() == offer_auth_addr.load()),
            # transfer amount <= offered amount
            Assert(royalty_asset_amount.get() <= offer_amt.load()),
            # Passed the correct account according to the policy
            Assert(payment_txn.get().xfer_asset() == payment_asset.asset_id()),
            # Make sure payments go to the right participants
            Assert(payment_txn.get().asset_receiver() == Application.address),
            Assert(royalty_receiver.address() == self.royalty_receiver),
        )

        return Seq(
            # Make sure transactions look right
            valid_transfer_group,
            ARC18.do_pay_assets(
                payment_txn.get().xfer_asset(),
                payment_txn.get().asset_amount(),
                owner.address(),
            ),
            # Perform asset move
            ARC18.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                buyer.address(),
                royalty_asset_amount.get(),
            ),
            # Clear listing from local state of owner
            ARC18.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                offer_auth_addr.load(),
                offer_amt.load() - royalty_asset_amount.get(),
                Txn.sender(),
                offered_amt.get(),
            ),
        )

    @external
    def offer(
        self,
        royalty_asset: abi.Asset,
        royalty_asset_amount: abi.Uint64,
        auth_address: abi.Address,
        prev_offer_amt: abi.Uint64,
        prev_offer_auth: abi.Address,
    ):
        """Flags that an asset is offered for sale and sets address authorized to submit the transfer"""
        return Seq(
            cb := AssetParam.clawback(royalty_asset.asset_id()),
            bal := AssetHolding.balance(Txn.sender(), royalty_asset.asset_id()),
            # Check that caller _has_ this asset
            Assert(bal.value() >= royalty_asset_amount.get()),
            # Check that this app is the clawback for it
            Assert(
                And(cb.hasValue(), cb.value() == Global.current_application_address())
            ),
            # Set the auth addr for this asset
            ARC18.do_update_offered(
                Txn.sender(),
                royalty_asset.asset_id(),
                auth_address.get(),
                royalty_asset_amount.get(),
                prev_offer_auth.get(),
                prev_offer_amt.get(),
            ),
        )

    @external
    def royalty_free_move(
        self,
        royalty_asset: abi.Asset,
        royalty_asset_amount: abi.Uint64,
        owner: abi.Account,
        receiver: abi.Account,
        offered_amt: abi.Uint64,
    ):
        """Moves the asset passed from one account to another"""

        return Seq(
            (offer := ScratchVar()).store(
                self.offers[royalty_asset.asset_id()][owner.address()]
            ),
            (curr_offer_amt := ScratchVar()).store(ARC18.offered_amount(offer.load())),
            (curr_offer_auth := ScratchVar()).store(ARC18.offered_auth(offer.load())),
            # Must match what is currently offered and amt to move is less than
            # or equal to what has been offered
            Assert(curr_offer_amt.load() == offered_amt.get()),
            Assert(curr_offer_amt.load() >= royalty_asset_amount.get()),
            Assert(curr_offer_auth.load() == Txn.sender()),
            # Delete the offer
            ARC18.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                Bytes(""),
                Int(0),
                curr_offer_auth.load(),
                curr_offer_amt.load(),
            ),
            # Move it
            ARC18.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                receiver.address(),
                royalty_asset_amount.get(),
            ),
        )

    ###
    # Read State
    ###

    Offer = abi.Tuple2[abi.Address, abi.Uint64]

    @external(read_only=True)
    def get_offer(
        self, royalty_asset: abi.Uint64, owner: abi.Account, *, output: Offer
    ):
        return output.decode(ARC18.offers[royalty_asset][owner.address()].get_must())

    Policy = abi.Tuple2[abi.Address, abi.Uint64]

    @external(read_only=True)
    def get_policy(self, *, output: Policy):
        return Seq(
            (addr := abi.Address()).decode(ARC18.royalty_receiver),
            (amt := abi.Uint64()).set(ARC18.royalty_basis),
            output.set(addr, amt),
        )

    @external(read_only=True)
    def get_administrator(self, *, output: abi.Address):
        return output.decode(ARC18.administrator)

    ###
    # Utils
    ###

    @Subroutine(TealType.uint64)
    def offered_amount(offer):
        return ExtractUint64(offer, Int(32))

    @Subroutine(TealType.bytes)
    def offered_auth(offer):
        return Extract(offer, Int(0), Int(32))

    @Subroutine(TealType.uint64)
    def compute_royalty_amount(payment_amt, royalty_basis):
        return WideRatio([payment_amt, royalty_basis], [ARC18.basis_point_multiplier])

    ###
    # Inner txn methods
    ###

    @Subroutine(TealType.none)
    def do_pay_assets(purchase_asset_id, purchase_amt, owner):
        royalty_amt = ScratchVar()
        return Seq(
            royalty_amt.store(
                ARC18.compute_royalty_amount(purchase_amt, ARC18.royalty_basis)
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: purchase_asset_id,
                    TxnField.asset_amount: purchase_amt - royalty_amt.load(),
                    TxnField.asset_receiver: owner,
                }
            ),
            If(
                royalty_amt.load() > Int(0),
                Seq(
                    InnerTxnBuilder.Next(),
                    InnerTxnBuilder.SetFields(
                        {
                            TxnField.type_enum: TxnType.AssetTransfer,
                            TxnField.xfer_asset: purchase_asset_id,
                            TxnField.asset_amount: royalty_amt.load(),
                            TxnField.asset_receiver: ARC18.royalty_receiver,
                        }
                    ),
                ),
            ),
            InnerTxnBuilder.Submit(),
        )

    @Subroutine(TealType.none)
    def do_pay_algos(purchase_amt, owner, royalty_receiver, royalty_basis):
        royalty_amt = ScratchVar()
        return Seq(
            royalty_amt.store(
                ARC18.compute_royalty_amount(purchase_amt, royalty_basis)
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.amount: purchase_amt - royalty_amt.load(),
                    TxnField.receiver: owner,
                }
            ),
            If(
                royalty_amt.load() > Int(0),
                Seq(
                    InnerTxnBuilder.Next(),
                    InnerTxnBuilder.SetFields(
                        {
                            TxnField.type_enum: TxnType.Payment,
                            TxnField.amount: royalty_amt.load(),
                            TxnField.receiver: royalty_receiver,
                        }
                    ),
                ),
            ),
            InnerTxnBuilder.Submit(),
        )

    @Subroutine(TealType.none)
    def do_move_asset(asset_id, from_addr, to_addr, asset_amt):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset_id,
                    TxnField.asset_amount: asset_amt,
                    TxnField.asset_sender: from_addr,
                    TxnField.asset_receiver: to_addr,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    @Subroutine(TealType.none)
    def do_update_offered(acct, asset, auth, amt, prev_auth, prev_amt):
        offer_state = ARC18.offers[asset]
        return Seq(
            previous := offer_state[acct].get_maybe(),
            # If we had something before, make sure its the same as what was passed. Otherwise make sure that a 0 was passed
            If(
                previous.hasValue(),
                Seq(
                    Assert(ARC18.offered_amount(previous.value()) == prev_amt),
                    Assert(ARC18.offered_auth(previous.value()) == prev_auth),
                ),
                Assert(And(prev_amt == Int(0), prev_auth == Global.zero_address())),
            ),
            # Now consider the new offer, if its 0 this is a delete, otherwise update
            If(
                amt > Int(0),
                offer_state[acct].set(Concat(auth, Itob(amt))),
                offer_state[acct].delete(),
            ),
        )


if __name__ == "__main__":
    import json

    arc18 = ARC18()

    print(arc18.approval_program)
    print(arc18.clear_program)
    print(json.dumps(arc18.contract.dictify()))
