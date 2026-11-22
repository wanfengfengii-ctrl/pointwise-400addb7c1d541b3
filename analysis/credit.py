from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class PairCredit:
    a: Fraction
    b: Fraction


def compute_pair_credit(none: Fraction, a: Fraction, b: Fraction, both: Fraction) -> PairCredit:
    return PairCredit(
        ((a - none) + (both - b)) / 2,
        ((b - none) + (both - a)) / 2,
    )
