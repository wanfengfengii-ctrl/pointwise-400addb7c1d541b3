import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from issue.availability import available_windows
from issue.catalog import IssueCatalog
from issue.conditions import REPAIR_CHOICES
from issue.responses import CandidateResponse, encode_responses
from station.revisions import RevisionStore
from station.shifts import Shift, encode_shift, validate_identifier


@dataclass(frozen=True)
class FrozenEvidence:
    issue_id: str
    station: str
    shift: Shift
    original: bytes


@dataclass(frozen=True)
class FrozenRiskEvidence:
    issue_id: str
    station: str
    shift: Shift
    campaign: str
    masses: tuple[Fraction, ...]
    original: bytes


def freeze(catalog: IssueCatalog, station: str, revision_number: int) -> FrozenEvidence:
    revision = RevisionStore(catalog.connection).get(station, revision_number)

    def build_original(issue_id: str) -> bytes:
        responses = tuple(
            CandidateResponse(tuple(
                available_windows(revision.order, candidate, choice) for choice in REPAIR_CHOICES
            ))
            for candidate in revision.order['candidates']
        )
        envelope = {
            'version': 1,
            'issue_id': issue_id,
            'station': revision.station,
            'shift': encode_shift(revision.shift),
            'body': encode_responses(responses),
        }
        return json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    issued = catalog.get_or_issue(revision.station, revision.number, build_original)
    return FrozenEvidence(issued.issue_id, issued.station, revision.shift, issued.original)


def _validate_campaign(campaign: object) -> str:
    return validate_identifier(campaign, '巡检批次')


def _validate_masses(masses: object, candidate_count: int) -> tuple[Fraction, ...]:
    if isinstance(masses, (str, bytes)) or not isinstance(masses, Sequence) or not masses:
        raise ValueError('候选占比须为非空序列')
    parsed = []
    for mass in masses:
        if isinstance(mass, bool):
            raise ValueError('候选占比须为非负有理数')
        if isinstance(mass, (int, Fraction)):
            value = Fraction(mass)
        elif isinstance(mass, str):
            try:
                value = Fraction(mass)
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError(f'非法候选占比 {mass!r}') from error
        else:
            raise ValueError('候选占比须为非负整数、Fraction 或有理数字符串')
        if value < 0:
            raise ValueError('候选占比不得为负')
        parsed.append(value)
    if len(parsed) != candidate_count:
        raise ValueError('候选占比数量须等于修订中的候选数')
    if sum(parsed, Fraction(0)) != 1:
        raise ValueError('候选占比之和须为 1')
    return tuple(parsed)


def freeze_risk(
    catalog: IssueCatalog,
    station: str,
    revision_number: int,
    campaign: object,
    masses: object,
) -> FrozenRiskEvidence:
    revision = RevisionStore(catalog.connection).get(station, revision_number)
    batch = _validate_campaign(campaign)
    weights = _validate_masses(masses, len(revision.order['candidates']))

    def build_original(issue_id: str) -> bytes:
        responses = tuple(
            CandidateResponse(tuple(
                available_windows(revision.order, candidate, choice) for choice in REPAIR_CHOICES
            ))
            for candidate in revision.order['candidates']
        )
        envelope = {
            'version': 2,
            'issue_id': issue_id,
            'station': revision.station,
            'shift': encode_shift(revision.shift),
            'body': {
                'campaign': batch,
                'masses': [str(mass) for mass in weights],
                **encode_responses(responses),
            },
        }
        return json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    issued = catalog.get_or_issue_risk(
        revision.station, revision.number, batch, weights, build_original
    )
    return FrozenRiskEvidence(
        issued.issue_id, issued.station, revision.shift, batch, weights, issued.original
    )
