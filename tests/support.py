import json
import sqlite3
import unittest
from contextlib import ExitStack, closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.bounds import CreditRange, CreditRanges
from demo import DOWNSTREAM, SHIFT, UPSTREAM, a_only_order, always_order
from issue.catalog import IssueCatalog
from issue.evidence import freeze
from receive.registry import EvidenceRegistry, accept
from reports.ledger import ReportLedger
from station.revisions import RevisionStore
from station.workorders import record


def ranges(a_min, a_max, b_min, b_max):
    return CreditRanges(
        CreditRange(Fraction(a_min), Fraction(a_max)),
        CreditRange(Fraction(b_min), Fraction(b_max)),
    )


def scenario(case_id, input_data, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': input_data,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, ensure_ascii=False, separators=(',', ':')))


class ExerciseCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='restart-test-')
        self.addCleanup(temporary.cleanup)
        self.connections = ExitStack()
        self.addCleanup(self.connections.close)
        self.root = Path(temporary.name)
        self.open_station()
        self.open_center()

    def open_station(self):
        self.station = self.connections.enter_context(closing(sqlite3.connect(self.root / 'station.db')))
        self.revisions, self.issues = RevisionStore(self.station), IssueCatalog(self.station)
        self.revisions.initialize()
        self.issues.initialize()

    def open_center(self):
        self.center = self.connections.enter_context(closing(sqlite3.connect(self.root / 'center.db')))
        self.registry, self.ledger = EvidenceRegistry(self.center), ReportLedger(self.center)
        self.registry.initialize()
        self.ledger.initialize()

    def freeze_order(self, station, order, shift=SHIFT):
        number = record(self.revisions, station, shift, order)
        return freeze(self.issues, station, number)

    def intake_order(self, station, order, shift=SHIFT):
        return accept(self.registry, self.freeze_order(station, order, shift).original)

    def stage_activation_pair(self, downstream_windows):
        up = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        down = self.intake_order(DOWNSTREAM, always_order(downstream_windows))
        return up, down

    def station_counts(self):
        (revisions,) = self.station.execute('SELECT COUNT(*) FROM workorder_revisions').fetchone()
        (issued,) = self.station.execute('SELECT COUNT(*) FROM issued_evidence').fetchone()
        return revisions, issued

    def published_counts(self):
        (reports,) = self.center.execute('SELECT COUNT(*) FROM reports').fetchone()
        (receipts,) = self.center.execute('SELECT COUNT(*) FROM success_receipts').fetchone()
        return reports, receipts

    def intake_count(self):
        return self.center.execute('SELECT COUNT(*) FROM received_evidence').fetchone()[0]

    def install_failed_commit(self):
        # The insert succeeds. SQLite checks the orphan at COMMIT.
        self.center.executescript('''
            CREATE TEMP TABLE fault_parent (id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE fault_child (
                report_number INTEGER REFERENCES fault_parent (id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TEMP TRIGGER reject_receipt_commit AFTER INSERT ON main.success_receipts
            BEGIN
                INSERT INTO fault_child VALUES (NEW.report_number);
            END;
        ''')
