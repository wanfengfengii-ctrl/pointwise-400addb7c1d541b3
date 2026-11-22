import json
from dataclasses import dataclass
from fractions import Fraction

from analysis.risk import ProbabilityRange, RiskOutcome
from receive.provenance import ReceivedSource
from station.shifts import decode_shift, encode_shift


@dataclass(frozen=True)
class RiskRequest:
    mean0: Fraction
    observed0: Fraction
    gap: Fraction


@dataclass(frozen=True)
class RiskReportSnapshot:
    report_number: int
    version: int
    campaign: str
    request: RiskRequest
    parents: tuple[ReceivedSource, ReceivedSource]
    outcome: RiskOutcome

    @property
    def batch(self) -> str:
        return self.campaign

    @property
    def mean0(self) -> Fraction:
        return self.request.mean0

    @property
    def observed0(self) -> Fraction:
        return self.request.observed0

    @property
    def gap(self) -> Fraction:
        return self.request.gap

    @property
    def status(self) -> str:
        return self.outcome.status

    @property
    def support(self) -> ProbabilityRange | None:
        return self.outcome.support

    @property
    def conditional(self) -> ProbabilityRange | None:
        return self.outcome.conditional


def _encode_source(source: ReceivedSource) -> dict:
    return {
        'received_id': source.received_id,
        'issue_id': source.issue_id,
        'station': source.station,
        'shift': encode_shift(source.shift),
        'fingerprint': source.fingerprint,
        'version': source.version,
    }


def _decode_source(value: dict) -> ReceivedSource:
    return ReceivedSource(
        value['received_id'], value['issue_id'], value['station'],
        decode_shift(value['shift']), value['fingerprint'], value['version'],
    )


def _encode_range(bounds: ProbabilityRange | None) -> list[str] | None:
    if bounds is None:
        return None
    return [str(bounds.minimum), str(bounds.maximum)]


def _decode_range(value: list[str] | None) -> ProbabilityRange | None:
    if value is None:
        return None
    lower, upper = value
    return ProbabilityRange(Fraction(lower), Fraction(upper))


def encode_risk(snapshot: RiskReportSnapshot) -> str:
    return json.dumps({
        'report_number': snapshot.report_number,
        'version': snapshot.version,
        'campaign': snapshot.campaign,
        'request': {
            'mean0': str(snapshot.request.mean0),
            'observed0': str(snapshot.request.observed0),
            'gap': str(snapshot.request.gap),
        },
        'parents': [_encode_source(source) for source in snapshot.parents],
        'status': snapshot.outcome.status,
        'support': _encode_range(snapshot.outcome.support),
        'conditional': _encode_range(snapshot.outcome.conditional),
    }, ensure_ascii=False, separators=(',', ':'))


def decode_risk(content: str) -> RiskReportSnapshot:
    data = json.loads(content)
    request = data['request']
    first, second = data['parents']
    outcome = RiskOutcome(
        data['status'], _decode_range(data['support']), _decode_range(data['conditional'])
    )
    return RiskReportSnapshot(
        data['report_number'], data['version'], data['campaign'],
        RiskRequest(Fraction(request['mean0']), Fraction(request['observed0']), Fraction(request['gap'])),
        (_decode_source(first), _decode_source(second)), outcome,
    )
