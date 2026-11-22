import json
import sqlite3
from dataclasses import dataclass

from station.shifts import Shift
from station.windows import parse_hour
from storage import is_record_number, write_transaction


class RevisionNotFound(LookupError):
    pass


@dataclass(frozen=True)
class WorkorderRevision:
    number: int
    station: str
    shift: Shift
    order: dict
    parent_number: int | None


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS workorder_revisions (
                number INTEGER PRIMARY KEY,
                station TEXT NOT NULL,
                shift_id TEXT NOT NULL,
                shift_start TEXT NOT NULL,
                shift_end TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_number INTEGER,
                UNIQUE (station, number),
                FOREIGN KEY (station, parent_number)
                    REFERENCES workorder_revisions (station, number)
            )
        ''')

    def append(
        self, station: str, shift: Shift, order: dict, parent_number: int | None = None
    ) -> int:
        content = json.dumps(order, ensure_ascii=False, separators=(',', ':'))
        with write_transaction(self.connection):
            cursor = self.connection.execute('''
                INSERT INTO workorder_revisions
                    (station, shift_id, shift_start, shift_end, content, parent_number)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (station, shift.shift_id, str(shift.start), str(shift.end), content, parent_number))
            number = cursor.lastrowid
        return number

    def get(self, station: str, revision_number: int) -> WorkorderRevision:
        if not isinstance(station, str) or not is_record_number(revision_number):
            raise RevisionNotFound((station, revision_number))
        row = self.connection.execute('''
            SELECT shift_id, shift_start, shift_end, content, parent_number
              FROM workorder_revisions WHERE station = ? AND number = ?
        ''', (station, revision_number)).fetchone()
        if row is None:
            raise RevisionNotFound((station, revision_number))
        shift_id, start, end, content, parent_number = row
        shift = Shift(shift_id, parse_hour(start), parse_hour(end))
        return WorkorderRevision(revision_number, station, shift, json.loads(content), parent_number)
