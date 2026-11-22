import json
from dataclasses import dataclass
from fractions import Fraction

from analysis.bounds import CreditRange, CreditRanges
from receive.provenance import ReceivedSource
from station.shifts import decode_shift, encode_shift


@dataclass(frozen=True)
class ReportSnapshot:
    report_number: int
    parents: tuple[ReceivedSource, ReceivedSource]
    credits: CreditRanges


def _encode_source(source: ReceivedSource) -> dict:
    return {
        'received_id': source.received_id,
        'issue_id': source.issue_id,
        'station': source.station,
        'shift': encode_shift(source.shift),
        'fingerprint': source.fingerprint,
    }


def _decode_source(value: dict) -> ReceivedSource:
    return ReceivedSource(
        value['received_id'], value['issue_id'], value['station'],
        decode_shift(value['shift']), value['fingerprint'],
    )


def encode_report(report: ReportSnapshot) -> str:
    return json.dumps({
        'report_number': report.report_number,
        'parents': [_encode_source(source) for source in report.parents],
        'credits': [
            [str(bounds.minimum), str(bounds.maximum)]
            for bounds in (report.credits.a, report.credits.b)
        ],
    }, ensure_ascii=False, separators=(',', ':'))


def _decode_range(value: list[str]) -> CreditRange:
    lower, upper = value
    return CreditRange(Fraction(lower), Fraction(upper))


def decode_report(content: str) -> ReportSnapshot:
    data = json.loads(content)
    first, second = data['parents']
    a, b = data['credits']
    return ReportSnapshot(
        data['report_number'], (_decode_source(first), _decode_source(second)),
        CreditRanges(_decode_range(a), _decode_range(b)),
    )
