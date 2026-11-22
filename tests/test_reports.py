import sqlite3
from fractions import Fraction

from demo import DOWNSTREAM, SHIFT, UPSTREAM, a_only_order, always_order
from issue.evidence import freeze
from receive.registry import accept
from receive.selection import SelectionError
from reports.history import ReportNotFound, read
from reports.publish import PublishError, publish
from station.corrections import correct
from station.revisions import RevisionNotFound
from station.shifts import Shift
from station.workorders import WorkorderError, record
from tests.support import ExerciseCase, ranges, scenario


class ReportTests(ExerciseCase):
    def test_wrong_shift(self):
        upstream = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        other_id = Shift('another-shift', Fraction(0), Fraction(2))
        other_coordinates = Shift(SHIFT.shift_id, Fraction(1), Fraction(3))
        wrong_ids = [
            self.intake_order(DOWNSTREAM, always_order([('1', '2')]), shift)
            for shift in (other_id, other_coordinates)
        ]
        self.station.close()
        for received_id in wrong_ids:
            with self.subTest(received_id=received_id):
                with self.assertRaises(SelectionError):
                    publish(self.ledger, upstream, received_id)
                self.assertEqual(self.published_counts(), (0, 0))
        self.assertEqual(self.intake_count(), 3)
        scenario(
            'v4', {'shift_ids': [SHIFT.shift_id, other_id.shift_id], 'both_durations': '2'},
            [0, 0], list(self.published_counts()), 3, self.intake_count(),
            ['receive/selection.py', 'reports/publish.py', 'reports/ledger.py'],
            '等长班次仍须比对身份和坐标。拒绝签发后既有三件实收保持。',
        )

    def test_same_station(self):
        first = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        second = self.intake_order(UPSTREAM, a_only_order([('1', '2')]))
        self.station.close()
        for ids in ((first, second), (first, first)):
            with self.subTest(ids=ids):
                with self.assertRaises(SelectionError):
                    publish(self.ledger, *ids)
        self.assertEqual(self.published_counts(), (0, 0))

    def test_missing_parent(self):
        first = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        self.station.close()
        with self.assertRaises(SelectionError):
            publish(self.ledger, first, first + 1)
        self.assertEqual(self.published_counts(), (0, 0))

    def _original_and_amended(self, replacement):
        upstream = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        old_revision = record(self.revisions, DOWNSTREAM, SHIFT, always_order([('1', '2')]))
        old_id = accept(self.registry, freeze(self.issues, DOWNSTREAM, old_revision).original)
        self.station.close()
        old_report = publish(self.ledger, upstream, old_id)
        self.open_station()
        new_revision = correct(self.revisions, DOWNSTREAM, old_revision, [
            {'rule_id': 'run', 'window_index': 0, 'window': replacement},
        ])
        new_id = accept(self.registry, freeze(self.issues, DOWNSTREAM, new_revision).original)
        self.station.close()
        new_report = publish(self.ledger, upstream, new_id)
        return old_report, new_report, (upstream, old_id, new_id)

    def test_amendment_and_reopen(self):
        old, new, (upstream, old_id, new_id) = self._original_and_amended(['1/2', '3/2'])
        self.assertEqual(old.snapshot.credits, ranges(0, 0, 0, 0))
        self.assertEqual(new.snapshot.credits, ranges('1/2', '1/2', 0, 0))
        self.assertEqual([p.received_id for p in old.snapshot.parents], [upstream, old_id])
        self.assertEqual([p.received_id for p in new.snapshot.parents], [upstream, new_id])
        self.center.close()
        self.open_center()
        for report in (old, new):
            received = read(self.ledger, report.snapshot.report_number)
            self.assertEqual(received, report)
        self.assertEqual(self.published_counts(), (2, 2))
        selected_old = publish(self.ledger, old_id, upstream)
        self.assertEqual(selected_old.snapshot.credits, old.snapshot.credits)
        self.assertEqual(selected_old.snapshot.parents, old.snapshot.parents[::-1])

    def test_partial_correction(self):
        upstream = self.intake_order(UPSTREAM, a_only_order([('0', '1'), ('3/2', '2')]))
        order = always_order([('1', '5/4'), ('3/2', '2')])
        revision = record(self.revisions, DOWNSTREAM, SHIFT, order)
        original_id = accept(self.registry, freeze(self.issues, DOWNSTREAM, revision).original)
        self.station.close()
        old = publish(self.ledger, upstream, original_id)
        self.open_station()
        corrected = correct(self.revisions, DOWNSTREAM, revision, [
            {'rule_id': 'run', 'window_index': 0, 'window': ['1/2', '5/4']},
        ])
        corrected_revision = self.revisions.get(DOWNSTREAM, corrected)
        self.assertEqual(corrected_revision.order['rules'][0]['windows'], [['1/2', '5/4'], ['3/2', '2']])
        self.assertEqual(corrected_revision.order['candidates'], order['candidates'])
        self.assertEqual(self.revisions.get(DOWNSTREAM, revision).order, order)
        corrected_id = accept(self.registry, freeze(self.issues, DOWNSTREAM, corrected).original)
        self.station.close()
        new = publish(self.ledger, upstream, corrected_id)
        self.center.close()
        self.open_center()
        self.assertEqual(old.snapshot.credits, ranges('1/2', '1/2', 0, 0))
        self.assertEqual(new.snapshot.credits, ranges(1, 1, 0, 0))
        self.assertEqual([p.received_id for p in old.snapshot.parents], [upstream, original_id])
        self.assertEqual([p.received_id for p in new.snapshot.parents], [upstream, corrected_id])
        self.assertEqual(read(self.ledger, old.snapshot.report_number), old)
        self.assertEqual(read(self.ledger, new.snapshot.report_number), new)

    def test_invalid_correction(self):
        order = always_order([('1', '2')])
        revision = record(self.revisions, DOWNSTREAM, SHIFT, order)
        changes = {'rule_id': 'run', 'window_index': 0, 'window': ['1/2', '3/2']}
        invalid_edits = [
            [], [dict(changes, window=['2', '1'])], [dict(changes, window_index=1)],
            [dict(changes, rule_id='missing')], [changes, changes],
        ]
        for edits in invalid_edits:
            with self.subTest(edits=edits):
                with self.assertRaises(WorkorderError):
                    correct(self.revisions, DOWNSTREAM, revision, edits)
        with self.assertRaises(RevisionNotFound):
            correct(self.revisions, DOWNSTREAM, revision + 1, [changes])
        self.assertEqual(self.station_counts(), (1, 0))
        self.assertEqual(self.revisions.get(DOWNSTREAM, revision).order, order)

    def test_exact_readback(self):
        old, new, _ = self._original_and_amended(['2/3', '5/3'])
        self.assertEqual(new.snapshot.credits, ranges('1/3', '1/3', 0, 0))
        self.center.close()
        self.open_center()
        old_read = read(self.ledger, old.snapshot.report_number)
        new_read = read(self.ledger, new.snapshot.report_number)
        self.assertEqual(old_read.snapshot.credits, ranges(0, 0, 0, 0))
        self.assertEqual(new_read.snapshot.credits, ranges('1/3', '1/3', 0, 0))
        self.assertEqual((old_read, new_read), (old, new))
        self.assertEqual(self.published_counts(), (2, 2))

    def test_unknown_report(self):
        with self.assertRaises(ReportNotFound):
            read(self.ledger, 1)
        self.assertEqual(self.published_counts(), (0, 0))

    def test_reinitialize(self):
        old, new, received_ids = self._original_and_amended(['1/2', '3/2'])
        before_intake = [self.registry.load(received_id) for received_id in received_ids]
        self.open_station()
        rows = self.station.execute('SELECT station, number FROM workorder_revisions ORDER BY number').fetchall()
        before_revisions = [self.revisions.get(station, number) for station, number in rows]
        before_issues = [freeze(self.issues, station, number) for station, number in rows]
        for store in (self.revisions, self.issues, self.registry, self.ledger):
            store.initialize()
            store.initialize()
        self.station.close()
        self.center.close()
        self.open_station()
        self.open_center()
        self.assertEqual(self.station_counts(), (3, 3))
        self.assertEqual(self.intake_count(), 3)
        self.assertEqual(self.published_counts(), (2, 2))
        self.assertEqual([self.revisions.get(station, number) for station, number in rows], before_revisions)
        self.assertEqual([freeze(self.issues, station, number) for station, number in rows], before_issues)
        self.assertEqual([self.registry.load(i) for i in received_ids], before_intake)
        self.assertEqual(read(self.ledger, old.snapshot.report_number), old)
        self.assertEqual(read(self.ledger, new.snapshot.report_number), new)

    def test_commit_failure(self):
        parent_ids = self.stage_activation_pair([('0', '1')])
        self.station.close()
        existing = publish(self.ledger, *parent_ids)
        attempted_number = existing.snapshot.report_number + 1
        self.install_failed_commit()
        with self.assertRaises(PublishError) as caught:
            publish(self.ledger, *parent_ids)
        self.assertIsInstance(caught.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(caught.exception.__cause__.sqlite_errorcode, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
        self.assertFalse(self.center.in_transaction)
        self.center.close()
        self.open_center()
        self.assertEqual(self.published_counts(), (1, 1))
        self.assertEqual(read(self.ledger, existing.snapshot.report_number), existing)
        with self.assertRaises(ReportNotFound):
            read(self.ledger, attempted_number)
        self.assertEqual(self.intake_count(), 2)
        scenario(
            'v8', {'committed_before_failure': 1, 'failed_receipt_report': attempted_number},
            [1, 1], list(self.published_counts()), 2, self.intake_count(),
            ['reports/publish.py', 'reports/ledger.py', 'storage.py'],
            '真实延迟外键使提交失败，旧定稿和两件实收保持，本次两笔写入同时撤销。',
        )

    def test_retry_after_rollback(self):
        parent_ids = self.stage_activation_pair([('1/2', '3/2')])
        self.station.close()
        self.install_failed_commit()
        with self.assertRaises(PublishError):
            publish(self.ledger, *parent_ids)
        self.center.close()
        self.open_center()
        self.assertEqual(self.published_counts(), (0, 0))
        retried = publish(self.ledger, *parent_ids)
        self.assertEqual(retried.snapshot.credits, ranges('1/2', '1/2', 0, 0))
        self.assertEqual([p.received_id for p in retried.snapshot.parents], list(parent_ids))
        self.assertEqual(retried.receipt.report_number, retried.snapshot.report_number)
        self.assertEqual(read(self.ledger, retried.snapshot.report_number), retried)
        self.assertEqual(self.published_counts(), (1, 1))
