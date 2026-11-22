from analysis.bounds import CreditRanges, bound_credits
from analysis.configurations import iter_configuration_pairs
from analysis.credit import compute_pair_credit
from analysis.overlap import common_hours
from receive.selection import SelectedEvidencePair


def evaluate(selection: SelectedEvidencePair) -> CreditRanges:
    credits = []
    for pair in iter_configuration_pairs(selection):
        hours = tuple(
            common_hours(first, second)
            for first, second in zip(pair.first.by_choice, pair.second.by_choice, strict=True)
        )
        credits.append(compute_pair_credit(*hours))
    return bound_credits(credits)
