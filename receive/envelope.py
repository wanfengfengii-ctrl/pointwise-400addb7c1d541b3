import json
from dataclasses import dataclass

from issue.responses import CandidateResponse, decode_responses
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


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError(f'原件有重复字段 {name}')
        fields[name] = value
    return fields


def validate_envelope(original: bytes) -> ValidatedEnvelope:
    if not isinstance(original, bytes):
        raise EvidenceError('原件须为 UTF-8 JSON 字节')
    try:
        envelope = json.loads(original.decode('utf-8'), object_pairs_hook=_unique_fields)
        if not isinstance(envelope, dict) or set(envelope) != {
            'version', 'issue_id', 'station', 'shift', 'body'
        }:
            raise ValueError('V1 原件外层字段不完整或含额外字段')
        if type(envelope['version']) is not int or envelope['version'] != 1:
            raise ValueError('仅支持 V1 原件')
        issue_id = validate_identifier(envelope['issue_id'], '发行号')
        station = validate_identifier(envelope['station'], '站点')
        shift = decode_shift(envelope['shift'])
        candidates = decode_responses(envelope['body'], shift)
    except (ValueError, RecursionError) as error:
        raise EvidenceError(f'站件校验失败：{error}') from error
    return ValidatedEnvelope(issue_id, station, shift, candidates, original)
