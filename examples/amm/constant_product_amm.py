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
            swap_amt = self._get_tokens_to_swap(
                amount, self.a_supply, self.b_supply, 1000, 0
            )
            self.a_supply -= swap_amt
            self.b_supply += amount
            return swap_amt

        swap_amt = self._get_tokens_to_swap(
            amount, self.b_supply, self.a_supply, 1000, 0
        )
        self.b_supply -= swap_amt
        self.a_supply += amount
        return swap_amt

    def _get_tokens_to_swap(self, in_amount, in_supply, out_supply, scale, fee) -> int:
        factor = scale - fee
        return (in_amount * factor * out_supply) / (
            (in_supply * scale) + (in_amount * factor)
        )

    def ratio(self):
        return self.a_supply / self.b_supply


class Simulator:
    def __init__(self):
        self.cpi = ConstantProductInvariant(
            a_supply=int(3e10),
            b_supply=int(1e9),
            issued=1000,
            supply=10000000,
            scale=1000,
            fee=3,
        )

        self.pool_supply = []
        self.a_supply = []
        self.b_supply = []
        self.swaps = []
        self.ratios = []

        self.a_swaps = []
        self.b_swaps = []
        self.deltas = []

    def run(self, num: int = 100):

        sizes = np.random.randint(1000, 1000000, num)

        for idx, size in enumerate(sizes):
            a_swap = size % 2 == 0

            if a_swap:
                size *= self.cpi.ratio()
            else:
                size /= self.cpi.ratio()

            self.a_swaps.append(size if a_swap else 0)
            self.b_swaps.append(size if not a_swap else 0)

            swapped = self.cpi.swap(size, a_swap)

            self.deltas.append(self.cpi.ratio() - size * swapped)

            self.swaps.append(swapped)
            self.ratios.append(self.cpi.ratio())
            self.pool_supply.append(self.cpi.supply)
            self.a_supply.append(self.cpi.a_supply)
            self.b_supply.append(self.cpi.b_supply)
