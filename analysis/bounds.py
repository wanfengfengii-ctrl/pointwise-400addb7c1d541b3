from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from analysis.credit import PairCredit


@dataclass(frozen=True)
class CreditRange:
    minimum: Fraction
    maximum: Fraction


@dataclass(frozen=True)
class CreditRanges:
    a: CreditRange
    b: CreditRange


def bound_credits(credits: Iterable[PairCredit]) -> CreditRanges:
    values = tuple(credits)
    a = [credit.a for credit in values]
    b = [credit.b for credit in values]
    return CreditRanges(CreditRange(min(a), max(a)), CreditRange(min(b), max(b)))
