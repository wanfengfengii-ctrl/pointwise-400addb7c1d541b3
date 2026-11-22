import json
from dataclasses import dataclass
from fractions import Fraction

from issue.responses import CandidateResponse, decode_candidates, decode_responses
from station.shifts import Shift, decode_shift, validate_identifier


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedEnvelope:
    issue_id: str
    station: str
    shift: Shift
    candidates: tuple[CandidateResponse, ...]
    original: bytes
    version: int = 1
    campaign: str | None = None
    masses: tuple[Fraction, ...] | None = None


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError(f'原件有重复字段 {name}')
        fields[name] = value
    return fields


def _decode_masses(value: object, candidate_count: int) -> tuple[Fraction, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError('V2 正文占比须为非空字符串列表')
    if len(value) != candidate_count:
        raise ValueError('V2 正文占比数量须等于候选数')
    parsed = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError('V2 正文占比须为有理数字符串')
        try:
            parsed.append(Fraction(item))
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f'V2 正文占比非法：{error}') from error
    if any(mass < 0 for mass in parsed):
        raise ValueError('V2 正文占比不得为负')
    if sum(parsed, Fraction(0)) != 1:
        raise ValueError('V2 正文占比之和须为 1')
    return tuple(parsed)


def _validate_v1(envelope: dict, issue_id: str, station: str, shift: Shift, original: bytes) -> ValidatedEnvelope:
    candidates = decode_responses(envelope['body'], shift)
    return ValidatedEnvelope(issue_id, station, shift, candidates, original)


def _validate_v2(envelope: dict, issue_id: str, station: str, shift: Shift, original: bytes) -> ValidatedEnvelope:
    body = envelope['body']
    if not isinstance(body, dict) or set(body) != {'campaign', 'masses', 'candidates'}:
        raise ValueError('V2 正文须包含 campaign、masses 和 candidates')
    campaign = validate_identifier(body['campaign'], '巡检批次')
    candidates = decode_candidates(body['candidates'], shift)
    masses = _decode_masses(body['masses'], len(candidates))
    return ValidatedEnvelope(issue_id, station, shift, candidates, original, 2, campaign, masses)


def validate_envelope(original: bytes) -> ValidatedEnvelope:
    if not isinstance(original, bytes):
        raise EvidenceError('原件须为 UTF-8 JSON 字节')
    try:
        envelope = json.loads(original.decode('utf-8'), object_pairs_hook=_unique_fields)
        if not isinstance(envelope, dict) or set(envelope) != {
            'version', 'issue_id', 'station', 'shift', 'body'
        }:
            raise ValueError('原件外层字段不完整或含额外字段')
        version = envelope['version']
        if type(version) is not int or version not in (1, 2):
            raise ValueError('仅支持 V1 或 V2 原件')
        issue_id = validate_identifier(envelope['issue_id'], '发行号')
        station = validate_identifier(envelope['station'], '站点')
        shift = decode_shift(envelope['shift'])
        if version == 1:
            return _validate_v1(envelope, issue_id, station, shift, original)
        return _validate_v2(envelope, issue_id, station, shift, original)
    except (ValueError, RecursionError) as error:
        raise EvidenceError(f'站件校验失败：{error}') from error
