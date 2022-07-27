from dataclasses import dataclass
import numpy as np
import random

# Python impl of constant product


@dataclass
class ConstantProductInvariant:
    a_supply: int
    b_supply: int

    issued: int
    supply: int

    scale: int
    fee: int

    def mint(self, a, b) -> int:
        to_mint = int(
            int(
                int(min(a / self.a_supply, b / self.b_supply) * self.scale)
                * self.issued
            )
            / self.scale
        )
        self.a_supply += a
        self.b_supply += b
        self.issued -= to_mint
        return to_mint

    def burn(self, amount) -> tuple[int, int]:
        # compute first
        burn_a, burn_b = self._burn_a(amount), self._burn_b(amount)

        self.a_supply -= burn_a
        self.b_supply -= burn_b
        # then add supply
        self.supply += amount
        return burn_a, burn_b

    def _burn_a(self, amount) -> int:
        return int((self.a_supply * amount) / self.issued)

    def _burn_b(self, amount) -> int:
        return int((self.b_supply * amount) / self.issued)

    def swap(self, amount: int, is_a: bool) -> int:

        if is_a:
            swap_amt = self._get_tokens_to_swap(amount, self.a_supply, self.b_supply)
            self.a_supply += amount
            self.b_supply -= swap_amt
            return swap_amt

        swap_amt = self._get_tokens_to_swap(amount, self.b_supply, self.a_supply)
        self.b_supply += amount
        self.a_supply -= swap_amt
        return swap_amt

    def _get_tokens_to_swap(self, in_amount, in_supply, out_supply) -> int:
        assert in_supply > 0
        assert out_supply > 0
        """ Constant product swap method with fixed input
                 
            X * Y = K

            X, Y are current supply of assets, goal is to keep K the same after adding in_amt and subtracting out amt 

            With no fees:
            ------------

            (X + X_in) * (Y - Y_out) = X*Y
            *Algebra happens*
            Y - ( X*Y / (X + X_in)) = Y_out

            With fees:
            ----------

            fee_factor = scale - fee (ex 1000, 3 for a .3% fee)

            X_adj = X_in * (fee_factor)

            (X + X_adj) * (Y - Y_out) = X*Y
            *Algebra happens*
            Y - ( X*Y / (X + X_adj)) = Y_out

            Or as in [Tinyman](https://github.com/tinymanorg/tinyman-contracts-v1/blob/main/contracts/validator_approval.teal#L1000): 
            Y_out = (X_adj * Y) / (X * scale + X_adj)
        """

        # Simple, no fees
        # out_amt = out_supply - ((in_supply * out_supply) / (in_supply + in_amount))

        factor = self.scale - self.fee
        out_amt = (in_amount * factor * out_supply) / (
            (in_supply * self.scale) + (in_amount * factor)
        )

        return int(out_amt)

    def scaled_ratio(self) -> int:
        return int((self.a_supply * self.scale) / self.b_supply)

    def ratio(self):
        return self.a_supply / self.b_supply


class Simulator:
    def __init__(self):
        self.cpi = ConstantProductInvariant(
            a_supply=int(3e7),
            b_supply=int(1e6),
            issued=1000,
            supply=10000000,
            scale=1000,
            fee=0,
        )

        self.pool_supply = []
        self.a_supply = []
        self.b_supply = []
        self.swaps = []
        self.ratios = []
        self.scaled_ratios = []

        self.a_swaps = []
        self.b_swaps = []
        self.deltas = []

    def run(self, num: int = 100):

        sizes = np.random.randint(10, 1000, num)

        self.sizes = sizes
        for idx, size in enumerate(sizes):
            a_swap = (idx + size) % 2 == 0

            if a_swap:
                size *= self.cpi.ratio()

            self.a_swaps.append(size if a_swap else 0)
            self.b_swaps.append(size if not a_swap else 0)

            swapped = self.cpi.swap(size, a_swap)

            if a_swap:
                self.deltas.append(
                    (self.cpi.scaled_ratio() - (size / swapped) * self.cpi.scale)
                    // self.cpi.scale
                )
            else:
                self.deltas.append(
                    (self.cpi.scaled_ratio() - (swapped / size) * self.cpi.scale)
                    // self.cpi.scale
                )

            self.scaled_ratios.append(self.cpi.scaled_ratio())
            self.swaps.append(swapped)
            self.ratios.append(self.cpi.ratio())
            self.a_supply.append(self.cpi.a_supply)
            self.b_supply.append(self.cpi.b_supply)

            self.pool_supply.append(self.cpi.supply)
