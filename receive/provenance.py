from dataclasses import dataclass
from hashlib import sha256

from receive.envelope import ValidatedEnvelope
from station.shifts import Shift


@dataclass(frozen=True)
class ReceivedSource:
    received_id: int
    issue_id: str
    station: str
    shift: Shift
    fingerprint: str


def fingerprint_evidence(original: bytes) -> str:
    return sha256(original).hexdigest()


def bind_received_source(received_id: int, envelope: ValidatedEnvelope) -> ReceivedSource:
    return ReceivedSource(
        received_id,
        envelope.issue_id,
        envelope.station,
        envelope.shift,
        fingerprint_evidence(envelope.original),
    )
