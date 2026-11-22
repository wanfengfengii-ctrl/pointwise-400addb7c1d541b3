from dataclasses import dataclass
from itertools import product
from typing import Iterator

from issue.responses import CandidateResponse
from receive.selection import SelectedEvidencePair


@dataclass(frozen=True)
class ConfigurationPair:
    first: CandidateResponse
    second: CandidateResponse


def iter_configuration_pairs(selection: SelectedEvidencePair) -> Iterator[ConfigurationPair]:
    for first, second in product(selection.first.envelope.candidates, selection.second.envelope.candidates):
        yield ConfigurationPair(first, second)
