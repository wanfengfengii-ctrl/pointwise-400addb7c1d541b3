import sqlite3
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from storage import write_transaction


@dataclass(frozen=True)
class IssuedRecord:
    station: str
    revision_number: int
    issue_id: str
    original: bytes


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
