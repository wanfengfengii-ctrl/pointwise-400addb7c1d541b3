import sqlite3
from dataclasses import dataclass

from receive.envelope import EvidenceError, ValidatedEnvelope, validate_envelope
from receive.provenance import ReceivedSource, bind_received_source, fingerprint_evidence
from station.shifts import encode_shift
from storage import is_record_number, write_transaction


class IntakeConflict(EvidenceError):
    pass


class EvidenceNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ReceivedEvidence:
    envelope: ValidatedEnvelope
    source: ReceivedSource


class EvidenceRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS received_evidence (
                received_id INTEGER PRIMARY KEY,
                issue_id TEXT NOT NULL UNIQUE,
                station TEXT NOT NULL,
                shift_id TEXT NOT NULL,
                shift_start TEXT NOT NULL,
                shift_end TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                original BLOB NOT NULL
            )
        ''')

    def _store(self, envelope: ValidatedEnvelope) -> int:
        shift = encode_shift(envelope.shift)
        fingerprint = fingerprint_evidence(envelope.original)
        with write_transaction(self.connection):
            row = self.connection.execute('''
                SELECT received_id, original FROM received_evidence WHERE issue_id = ?
            ''', (envelope.issue_id,)).fetchone()
            if row is None:
                cursor = self.connection.execute('''
                    INSERT INTO received_evidence
                        (issue_id, station, shift_id, shift_start, shift_end, fingerprint, original)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    envelope.issue_id, envelope.station, shift['id'], shift['start'],
                    shift['end'], fingerprint, envelope.original,
                ))
                received_id = cursor.lastrowid
            else:
                received_id, stored_original = row
                if stored_original != envelope.original:
                    raise IntakeConflict(f'发行号 {envelope.issue_id} 已绑定另一原件')
        return received_id

    def load(self, received_id: int) -> ReceivedEvidence:
        if not is_record_number(received_id):
            raise EvidenceNotFound(received_id)
        row = self.connection.execute('''
            SELECT original, issue_id, station, shift_id, shift_start, shift_end, fingerprint
              FROM received_evidence WHERE received_id = ?
        ''', (received_id,)).fetchone()
        if row is None:
            raise EvidenceNotFound(received_id)
        original, *binding = row
        envelope = validate_envelope(original)
        source = bind_received_source(received_id, envelope)
        shift = encode_shift(source.shift)
        if binding != [
            source.issue_id, source.station, shift['id'], shift['start'], shift['end'], source.fingerprint
        ]:
            raise EvidenceError(f'实收号 {received_id} 的原件与来源绑定不一致')
        return ReceivedEvidence(envelope, source)


def accept(registry: EvidenceRegistry, original: bytes) -> int:
    return registry._store(validate_envelope(original))
