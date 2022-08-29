from typing import Final
from pyteal import (
    Reject,
    abi,
    TealType,
    Subroutine,
    Itob,
    Assert,
    Global,
    Bytes,
    Int,
    Seq,
    Txn,
    If,
    And,
    InnerTxnBuilder,
    ScratchVar,
    TxnField,
    TxnType,
    Not,
    WideRatio,
    Concat,
)

from beaker import (
    Application,
    ApplicationStateValue,
    DynamicAccountStateValue,
    Authorize,
    external,
    internal,
    create,
    update,
    delete,
    opt_in,
)


class ARC18(Application):
    class Offer(abi.NamedTuple):
        auth_address: abi.Field[abi.Address]
        amount: abi.Field[abi.Uint64]

    class RoyaltyPolicy(abi.NamedTuple):
        receiver: abi.Field[abi.Address]
        basis: abi.Field[abi.Uint64]

    administrator: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes, key=Bytes("admin"), default=Global.creator_address()
    )

    royalty_basis: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64
    )

    royalty_receiver: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes
    )

    offers: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=14,
        key_gen=Subroutine(TealType.bytes)(lambda x: Itob(x)),
    )

    # A basis point is 1/100 of 1%
    _basis_point_multiplier: Final[int] = 100 * 100
    basis_point_multiplier: Final[Int] = Int(_basis_point_multiplier)

    ###
    # App Lifecycle
    ###

    @create
    def create(self):
        return self.initialize_application_state()

    @update
    def update(self):
        return Assert(Txn.sender() == self.administrator)

    @delete
    def delete(self):
        return Assert(Txn.sender() == self.administrator)

    @opt_in
    def opt_in(self):
        return self.initialize_account_state()

    ###
    # Admin
    ###

    @external(authorize=Authorize.only(administrator))
    def set_administrator(self, new_admin: abi.Address):
        """Sets the administrator for this royalty enforcer"""
        return self.administrator.set(new_admin.get())

    @external(authorize=Authorize.only(administrator))
    def set_policy(self, royalty_policy: RoyaltyPolicy):
        """Sets the royalty basis and royalty receiver for this royalty enforcer"""
        return Seq(
            (basis := abi.Uint64()).set(royalty_policy.basis),
            (rcv := abi.Address()).set(royalty_policy.receiver),
            Assert(basis.get() <= self.basis_point_multiplier),
            self.royalty_basis.set(basis.get()),
            self.royalty_receiver.set(rcv.encode()),
        )

    @external(authorize=Authorize.only(administrator))
    def set_payment_asset(self, payment_asset: abi.Asset, is_allowed: abi.Bool):
        """Triggers the contract account to opt in or out of an asset that may be used for payment of royalties"""
        return Seq(
            bal := payment_asset.holding(self.address).balance(),
            creator := payment_asset.params().creator_address(),
            If(And(is_allowed.get(), Not(bal.hasValue())))
            .Then(
                # Opt in to asset
                InnerTxnBuilder.Execute(
                    {
                        TxnField.type_enum: TxnType.AssetTransfer,
                        TxnField.xfer_asset: payment_asset.asset_id(),
                        TxnField.asset_amount: Int(0),
                        TxnField.fee: Int(0),
                        TxnField.asset_receiver: self.address,
                    }
                )
            )
            .ElseIf(And(Not(is_allowed.get()), bal.hasValue()))
            .Then(
                # Opt out, close asset to asset creator
                InnerTxnBuilder.Execute(
                    {
                        TxnField.type_enum: TxnType.AssetTransfer,
                        TxnField.xfer_asset: payment_asset.asset_id(),
                        TxnField.asset_amount: Int(0),
                        TxnField.fee: Int(0),
                        TxnField.asset_close_to: creator.value(),
                        TxnField.asset_receiver: creator.value(),
                    }
                )
            )
            .Else(Reject()),
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
        valid_transfer_group = Seq(
            (offer := abi.make(self.Offer)).decode(
                self.offers[royalty_asset.asset_id()][owner.address()]
            ),
            (offer_amt := abi.Uint64()).set(offer.amount),
            (offer_auth := abi.Address()).set(offer.auth_address),
            Assert(
                Global.group_size() == Int(2),
                # App call sent by authorizing address
                Txn.sender() == offer_auth.get(),
                # transfer amount <= offered amount
                royalty_asset_amount.get() <= offer_amt.get(),
                # Make sure payments are going to the right participants
                payment_txn.get().receiver() == self.address,
                royalty_receiver.address() == self.royalty_receiver,
            ),
        )

        return Seq(
            # Make sure transactions look right
            valid_transfer_group,
            # Make royalty payment
            self.do_pay_algos(
                payment_txn.get().amount(),
                owner.address(),
                royalty_receiver.address(),
                self.royalty_basis,
            ),
            # Perform asset move
            self.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                buyer.address(),
                royalty_asset_amount.get(),
            ),
            # Clear listing from local state of owner
            self.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                offer_auth.get(),
                offer_amt.get() - royalty_asset_amount.get(),
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

        valid_transfer_group = Seq(
            # Get the offer from local state
            (offer := abi.make(self.Offer)).decode(
                self.offers[royalty_asset.asset_id()][owner.address()]
            ),
            (offer_amt := abi.Uint64()).set(offer.amount),
            (offer_auth := abi.Address()).set(offer.auth_address),
            Assert(
                Global.group_size() == Int(2),
                # App call sent by authorizing address
                Txn.sender() == offer_auth.get(),
                # payment txn should be from auth
                payment_txn.get().sender() == offer_auth.get(),
                # transfer amount <= offered amount
                royalty_asset_amount.get() <= offer_amt.get(),
                # Passed the correct account according to the policy
                payment_txn.get().xfer_asset() == payment_asset.asset_id(),
                # Make sure payments go to the right participants
                payment_txn.get().asset_receiver() == self.address,
                royalty_receiver.address() == self.royalty_receiver,
            ),
        )

        return Seq(
            # Make sure transactions look right
            valid_transfer_group,
            self.do_pay_assets(
                payment_txn.get().xfer_asset(),
                payment_txn.get().asset_amount(),
                owner.address(),
            ),
            # Perform asset move
            self.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                buyer.address(),
                royalty_asset_amount.get(),
            ),
            # Clear listing from local state of owner
            self.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                offer_auth.get(),
                offer_amt.get() - royalty_asset_amount.get(),
                Txn.sender(),
                offered_amt.get(),
            ),
        )

    @external
    def offer(
        self,
        royalty_asset: abi.Asset,
        offer: Offer,
        previous_offer: Offer,
    ):
        """Flags that an asset is offered for sale and sets address authorized to submit the transfer"""
        return Seq(
            (offer_amt := abi.Uint64()).set(offer.amount),
            (offer_auth := abi.Address()).set(offer.auth_address),
            (prev_amt := abi.Uint64()).set(previous_offer.amount),
            (prev_auth := abi.Address()).set(previous_offer.auth_address),
            bal := royalty_asset.holding(Txn.sender()).balance(),
            cb := royalty_asset.params().clawback_address(),
            Assert(
                # Check that caller _has_ this asset
                bal.value() >= offer_amt.get(),
                # Check that this app is the clawback for it
                cb.value() == self.address,
                # Rest of the checks done in do_update_offered
            ),
            # Set the auth addr for this asset
            self.do_update_offered(
                Txn.sender(),
                royalty_asset.asset_id(),
                offer_auth.get(),
                offer_amt.get(),
                prev_auth.get(),
                prev_amt.get(),
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
            (offer := abi.make(self.Offer)).decode(
                self.offers[royalty_asset.asset_id()][owner.address()]
            ),
            (curr_offer_amt := abi.Uint64()).set(offer.amount),
            (curr_offer_auth := abi.Address()).set(offer.auth_address),
            # Must match what is currently offered and amt to move is less than
            # or equal to what has been offered
            Assert(
                curr_offer_amt.get() == offered_amt.get(),
                curr_offer_amt.get() >= royalty_asset_amount.get(),
                curr_offer_auth.get() == Txn.sender(),
            ),
            # Delete the offer
            self.do_update_offered(
                owner.address(),
                royalty_asset.asset_id(),
                Bytes(""),
                Int(0),
                curr_offer_auth.get(),
                curr_offer_amt.get(),
            ),
            # Move it
            self.do_move_asset(
                royalty_asset.asset_id(),
                owner.address(),
                receiver.address(),
                royalty_asset_amount.get(),
            ),
        )

    ###
    # Read State
    ###

    @external(read_only=True)
    def get_offer(
        self, royalty_asset: abi.Uint64, owner: abi.Account, *, output: Offer
    ):
        """get the offered details for an owner by asset id"""
        return output.decode(
            self.offers[royalty_asset.get()][owner.address()].get_must()
        )

    @external(read_only=True)
    def get_policy(self, *, output: RoyaltyPolicy):
        """get the royalty policy for this application"""
        return Seq(
            (basis := abi.Uint64()).set(self.royalty_basis.get_must()),
            (rcv := abi.Address()).set(self.royalty_receiver.get_must()),
            output.set(rcv, basis),
        )

    @external(read_only=True)
    def get_administrator(self, *, output: abi.Address):
        """get the current administrator for this application"""
        return output.decode(self.administrator)

    ###
    # Utils
    ###

    def compute_royalty_amount(self, payment_amt, royalty_basis):
        return WideRatio([payment_amt, royalty_basis], [self.basis_point_multiplier])

    ###
    # Inner txn methods
    ###

    @internal(TealType.none)
    def do_pay_assets(self, purchase_asset_id, purchase_amt, owner):
        royalty_amt = ScratchVar()
        return Seq(
            royalty_amt.store(
                self.compute_royalty_amount(purchase_amt, self.royalty_basis)
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: purchase_asset_id,
                    TxnField.asset_amount: purchase_amt - royalty_amt.load(),
                    TxnField.asset_receiver: owner,
                    TxnField.fee: Int(0),
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
                            TxnField.asset_receiver: self.royalty_receiver,
                            TxnField.fee: Int(0),
                        }
                    ),
                ),
            ),
            InnerTxnBuilder.Submit(),
        )

    @internal(TealType.none)
    def do_pay_algos(self, purchase_amt, owner, royalty_receiver, royalty_basis):
        royalty_amt = ScratchVar()
        return Seq(
            royalty_amt.store(self.compute_royalty_amount(purchase_amt, royalty_basis)),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.Payment,
                    TxnField.amount: purchase_amt - royalty_amt.load(),
                    TxnField.receiver: owner,
                    TxnField.fee: Int(0),
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
                            TxnField.fee: Int(0),
                        }
                    ),
                ),
            ),
            InnerTxnBuilder.Submit(),
        )

    @internal(TealType.none)
    def do_move_asset(asset_id, from_addr, to_addr, asset_amt):
        return InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: asset_id,
                TxnField.asset_amount: asset_amt,
                TxnField.asset_sender: from_addr,
                TxnField.asset_receiver: to_addr,
                TxnField.fee: Int(0),
            }
        )

    @internal(TealType.none)
    def do_update_offered(self, acct, asset, auth, amt, prev_auth, prev_amt):
        return Seq(
            previous := self.offers[asset][acct].get_maybe(),
            # If we had something before, make sure its the same as what was passed. Otherwise make sure that a 0 was passed
            If(
                previous.hasValue(),
                Seq(
                    (prev_offer := abi.make(self.Offer)).decode(previous.value()),
                    prev_offer.amount.use(lambda amt: Assert(amt.get() == prev_amt)),
                    prev_offer.auth_address.use(
                        lambda addr: Assert(addr.get() == prev_auth)
                    ),
                ),
                Assert(prev_amt == Int(0), prev_auth == Global.zero_address()),
            ),
            # Now consider the new offer, if its 0 this is a delete, otherwise update
            If(
                amt > Int(0),
                # Cheat since we know the encoding
                self.offers[asset][acct].set(Concat(auth, Itob(amt))),
                self.offers[asset][acct].delete(),
            ),
        )


if __name__ == "__main__":
    import json

    arc18 = ARC18()

    print(arc18.approval_program)
    print(arc18.clear_program)
    print(json.dumps(arc18.contract.dictify()))
