import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable
from uuid import uuid4

from storage import write_transaction


@dataclass(frozen=True)
class IssuedRecord:
    station: str
    revision_number: int
    issue_id: str
    original: bytes


@dataclass(frozen=True)
class IssuedRiskRecord(IssuedRecord):
    campaign: str
    masses: tuple[Fraction, ...]


class RiskIssueConflict(ValueError):
    pass


class IssueCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS issued_evidence (
                station TEXT NOT NULL,
                revision_number INTEGER NOT NULL,
                issue_id TEXT NOT NULL UNIQUE,
                original BLOB NOT NULL,
                PRIMARY KEY (station, revision_number),
                FOREIGN KEY (station, revision_number)
                    REFERENCES workorder_revisions (station, number)
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS issued_risk_evidence (
                station TEXT NOT NULL,
                revision_number INTEGER NOT NULL,
                campaign TEXT NOT NULL,
                issue_id TEXT NOT NULL UNIQUE,
                masses TEXT NOT NULL,
                original BLOB NOT NULL,
                PRIMARY KEY (station, revision_number, campaign),
                FOREIGN KEY (station, revision_number)
                    REFERENCES workorder_revisions (station, number)
            )
        ''')

    def get_or_issue(
        self, station: str, revision_number: int, build_original: Callable[[str], bytes]
    ) -> IssuedRecord:
        with write_transaction(self.connection):
            row = self.connection.execute('''
                SELECT issue_id, original FROM issued_evidence
                 WHERE station = ? AND revision_number = ?
            ''', (station, revision_number)).fetchone()
            if row is None:
                issue_id = uuid4().hex
                original = build_original(issue_id)
                self.connection.execute('''
                    INSERT INTO issued_evidence (station, revision_number, issue_id, original)
                    VALUES (?, ?, ?, ?)
                ''', (station, revision_number, issue_id, original))
            else:
                issue_id, original = row
        return IssuedRecord(station, revision_number, issue_id, original)

    def get_or_issue_risk(
        self,
        station: str,
        revision_number: int,
        campaign: str,
        masses: tuple[Fraction, ...],
        build_original: Callable[[str], bytes],
    ) -> IssuedRiskRecord:
        encoded = encode_masses(masses)
        with write_transaction(self.connection):
            row = self.connection.execute('''
                SELECT issue_id, masses, original FROM issued_risk_evidence
                 WHERE station = ? AND revision_number = ? AND campaign = ?
            ''', (station, revision_number, campaign)).fetchone()
            if row is None:
                issue_id = uuid4().hex
                original = build_original(issue_id)
                self.connection.execute('''
                    INSERT INTO issued_risk_evidence
                        (station, revision_number, campaign, issue_id, masses, original)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (station, revision_number, campaign, issue_id, encoded, original))
            else:
                issue_id, stored_masses, original = row
                if stored_masses != encoded:
                    raise RiskIssueConflict(
                        f'站点 {station} 修订 {revision_number} 批次 {campaign} 已冻结另一组占比'
                    )
        return IssuedRiskRecord(station, revision_number, issue_id, original, campaign, masses)


def encode_masses(masses: tuple[Fraction, ...]) -> str:
    return json.dumps([str(mass) for mass in masses], separators=(',', ':'))
