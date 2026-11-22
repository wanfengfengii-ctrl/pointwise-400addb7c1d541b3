import json
from fractions import Fraction

from analysis.risk import ProbabilityRange
from demo import DOWNSTREAM, UPSTREAM, always_order
from issue.catalog import RiskIssueConflict
from issue.evidence import freeze, freeze_risk
from receive.envelope import EvidenceError
from receive.registry import accept
from receive.risk_selection import RiskSelectionError
from reports.history import ReportNotFound, read_risk
from reports.publish import RiskPublishError, publish, publish_risk
from station.shifts import Shift
from station.workorders import record
from tests.support import ExerciseCase, scenario

THREE_HOURS = Shift('three-hour-shift', Fraction(0), Fraction(3))


def risk_order(order_id, candidates):
    """Build a workorder from per-candidate (choice, windows) pairs."""
    devices, configurations, rules = [], [], []
    for index, pairs in enumerate(candidates):
        device = f'private-sensor-{index}'
        devices.append(device)
        configurations.append({'id': f'private-unit-{index}', 'enabled': [device]})
        for choice, windows in pairs:
            rules.append({
                'id': f'private-rule-{index}-{choice}',
                'requires': [device],
                'choices': [choice],
                'windows': [list(window) for window in windows],
            })
    return {
        'workorder_id': order_id,
        'devices': devices,
        'candidates': configurations,
        'rules': rules,
    }


# Responses giving the public sample none-repair matrix F0 = [[0,1],[1,2]] on [0,3).
LEFT_SAMPLE = [
    [('none', [('0', '1')]), ('A', [('0', '1')]), ('AB', [('0', '1')])],
    [('none', [('0', '3')]), ('A', [('0', '3')]), ('B', [('0', '3')]), ('AB', [('0', '3')])],
]
RIGHT_SAMPLE = [
    [('none', [('2', '3')]), ('A', [('2', '3')]), ('B', [('2', '3')]), ('AB', [('2', '3')])],
    [('none', [('0', '2')]), ('A', [('0', '2')]), ('B', [('0', '1')]), ('AB', [('0', '2')])],
]


class RiskTests(ExerciseCase):
    def risk_counts(self):
        (reports,) = self.center.execute('SELECT COUNT(*) FROM risk_reports').fetchone()
        (receipts,) = self.center.execute('SELECT COUNT(*) FROM risk_receipts').fetchone()
        return reports, receipts

    def risk_station(self, station, order_id, candidates, *, campaign='巡检-01', masses=('1/2', '1/2')):
        number = record(self.revisions, station, THREE_HOURS, risk_order(order_id, candidates))
        return number, freeze_risk(self.issues, station, number, campaign, list(masses))

    def sample_pair(self):
        left_number, left = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        right_number, right = self.risk_station(DOWNSTREAM, 'right', RIGHT_SAMPLE, masses=('1/4', '3/4'))
        left_id = accept(self.registry, left.original)
        right_id = accept(self.registry, right.original)
        return (left_number, right_number, left, right), (left_id, right_id)

    def balanced_pair(self):
        left_number, left = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        right_number, right = self.risk_station(
            DOWNSTREAM, 'balanced', RIGHT_SAMPLE, masses=('1/2', '1/2'))
        left_id = accept(self.registry, left.original)
        right_id = accept(self.registry, right.original)
        return (left_number, right_number), (left_id, right_id)

    def test_freeze_shape_and_retry(self):
        number, artifact = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        wire = json.loads(artifact.original)
        self.assertEqual(wire['version'], 2)
        self.assertEqual(wire['body']['campaign'], '巡检-01')
        self.assertEqual(wire['body']['masses'], ['1/2', '1/2'])
        self.assertEqual(wire['body']['candidates'][0]['none'], [['0', '1']])
        self.assertNotIn(b'private-sensor', artifact.original)
        self.assertNotIn(b'private-unit', artifact.original)
        retry = freeze_risk(self.issues, UPSTREAM, number, '巡检-01', ['1/2', '1/2'])
        self.assertEqual(retry, artifact)
        self.assertEqual(retry.original, artifact.original)
        self.assertEqual(retry.issue_id, artifact.issue_id)
        self.assertEqual(self.station_counts(), (1, 0))
        (risk_rows,) = self.station.execute('SELECT COUNT(*) FROM issued_risk_evidence').fetchone()
        self.assertEqual(risk_rows, 1)

    def test_freeze_rejects_changed_masses(self):
        number, _ = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        with self.assertRaises(RiskIssueConflict):
            freeze_risk(self.issues, UPSTREAM, number, '巡检-01', ['1/4', '3/4'])
        self.assertEqual(self.station_counts(), (1, 0))
        (risk_rows,) = self.station.execute('SELECT COUNT(*) FROM issued_risk_evidence').fetchone()
        self.assertEqual(risk_rows, 1)

    def test_freeze_rejects_invalid_masses(self):
        record(self.revisions, UPSTREAM, THREE_HOURS, risk_order('private', LEFT_SAMPLE))
        for masses in ([], ['1/2'], ['1/2', '1/2', '0'], ['-1/2', '3/2'], ['x', '1'],
                       [True, '1'], ['1/0', '1'], [1.5, '-0.5']):
            with self.subTest(masses=masses):
                with self.assertRaises(ValueError):
                    freeze_risk(self.issues, UPSTREAM, 1, '巡检-01', masses)
        self.assertEqual(self.station_counts(), (1, 0))

    def test_v1_and_v2_are_distinct(self):
        number = record(self.revisions, UPSTREAM, THREE_HOURS, risk_order('private', LEFT_SAMPLE))
        v1 = freeze(self.issues, UPSTREAM, number)
        v2 = freeze_risk(self.issues, UPSTREAM, number, '巡检-01', ['1/2', '1/2'])
        self.assertNotEqual(v1.issue_id, v2.issue_id)
        self.assertNotEqual(v1.original, v2.original)
        self.assertEqual(self.station_counts(), (1, 1))
        # A V2 freeze does not disturb the V1 issue record.
        self.assertEqual(freeze(self.issues, UPSTREAM, number), v1)

    def test_public_samples(self):
        (left_number, right_number, left, right), (left_id, right_id) = self.sample_pair()
        balanced_number, balanced_artifact = self.risk_station(
            DOWNSTREAM, 'balanced', RIGHT_SAMPLE, masses=('1/2', '1/2'))
        balanced_id = accept(self.registry, balanced_artifact.original)
        self.station.close()

        observed = publish_risk(self.ledger, left_id, right_id, Fraction(5, 4), Fraction(1), Fraction(1))
        balanced = publish_risk(self.ledger, left_id, balanced_id, Fraction(1), Fraction(1), Fraction(1))
        unsupported = publish_risk(self.ledger, left_id, balanced_id, Fraction(1), Fraction(3), Fraction(1))
        inconsistent = publish_risk(self.ledger, left_id, right_id, Fraction(0), Fraction(1), Fraction(1))

        self.assertEqual(observed.snapshot.outcome.status, 'ok')
        self.assertEqual(observed.snapshot.outcome.support, ProbabilityRange(Fraction(1, 4), Fraction(3, 4)))
        self.assertEqual(observed.snapshot.outcome.conditional, ProbabilityRange(Fraction(2, 3), Fraction(1)))
        self.assertEqual(balanced.snapshot.outcome.status, 'ok')
        self.assertEqual(balanced.snapshot.outcome.support, ProbabilityRange(Fraction(0), Fraction(1)))
        self.assertEqual(balanced.snapshot.outcome.conditional, ProbabilityRange(Fraction(1, 2), Fraction(1, 2)))
        self.assertEqual(unsupported.snapshot.outcome.status, 'unsupported')
        self.assertEqual(unsupported.snapshot.outcome.support, ProbabilityRange(Fraction(0), Fraction(0)))
        self.assertIsNone(unsupported.snapshot.outcome.conditional)
        self.assertEqual(inconsistent.snapshot.outcome.status, 'inconsistent')
        self.assertIsNone(inconsistent.snapshot.outcome.support)
        self.assertIsNone(inconsistent.snapshot.outcome.conditional)
        for report in (observed, balanced, unsupported, inconsistent):
            self.assertEqual(report.snapshot.version, 2)
            self.assertEqual(report.snapshot.campaign, '巡检-01')
            self.assertEqual(len(report.snapshot.parents), 2)
        def rendered(value):
            return None if value is None else [[str(value.minimum), str(value.maximum)]]

        scenario(
            'v9',
            {'F0': [[0, 1], [1, 2]], 'left': ['1/2', '1/2'], 'right': ['1/4', '3/4']},
            [[['1/4', '3/4']], [['2/3', '1']], [['0', '1']], [['1/2', '1/2']], [['0', '0']], None, None],
            [rendered(observed.snapshot.outcome.support), rendered(observed.snapshot.outcome.conditional),
             rendered(balanced.snapshot.outcome.support), rendered(balanced.snapshot.outcome.conditional),
             rendered(unsupported.snapshot.outcome.support), rendered(unsupported.snapshot.outcome.conditional),
             rendered(inconsistent.snapshot.outcome.support)],
            [left_number, right_number], [left_number, balanced_number],
            ['issue/evidence.py', 'analysis/risk.py', 'reports/publish.py'],
            '两站占比与共同工时约束出一族联合分布；支持集与条件集都取相容顶点上的精确端点。',
        )

    def test_exact_retry_reuses_receipt(self):
        _, artifact = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        first = accept(self.registry, artifact.original)
        before = self.registry.load(first)
        self.center.close()
        self.open_center()
        second = accept(self.registry, artifact.original)
        self.assertEqual(first, second)
        self.assertEqual(self.registry.load(second), before)
        self.assertEqual(self.intake_count(), 1)

    def test_reject_mixed_and_mismatched_pairs(self):
        _, left = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        _, right = self.risk_station(
            DOWNSTREAM, 'right', RIGHT_SAMPLE, masses=('1/4', '3/4'))
        v1_id = self.intake_order(UPSTREAM, always_order([('0', '1')]))
        left_id = accept(self.registry, left.original)
        right_id = accept(self.registry, right.original)
        right_number = record(self.revisions, DOWNSTREAM, THREE_HOURS, risk_order(
            'other-campaign', RIGHT_SAMPLE))
        other_campaign = accept(self.registry, freeze_risk(
            self.issues, DOWNSTREAM, right_number, '巡检-02', ['1/4', '3/4']
        ).original)
        self.station.close()
        # A V1 intake cannot stand in for either V2 parent.
        for ids in ((v1_id, right_id), (left_id, v1_id), (left_id, other_campaign)):
            with self.subTest(ids=ids):
                with self.assertRaises(RiskSelectionError):
                    publish_risk(self.ledger, *ids, Fraction(1), Fraction(1), Fraction(1))
        self.assertEqual(self.published_counts(), (0, 0))
        self.assertEqual(self.risk_counts(), (0, 0))

    def test_reject_same_station_and_shift(self):
        _, left = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        _, copy = self.risk_station(UPSTREAM, 'left-copy', LEFT_SAMPLE)
        left_id = accept(self.registry, left.original)
        copy_id = accept(self.registry, copy.original)
        self.assertNotEqual(left_id, copy_id)  # Two revisions, two issue numbers.
        other_shift_number = record(self.revisions, DOWNSTREAM, Shift(
            THREE_HOURS.shift_id, Fraction(0), Fraction(4)), risk_order('wide', RIGHT_SAMPLE))
        wide = freeze_risk(self.issues, DOWNSTREAM, other_shift_number, '巡检-01', ['1/4', '3/4'])
        wide_id = accept(self.registry, wide.original)
        self.station.close()
        with self.assertRaises(RiskSelectionError):
            publish_risk(self.ledger, left_id, copy_id, Fraction(1), Fraction(1), Fraction(1))
        with self.assertRaises(RiskSelectionError):
            publish_risk(self.ledger, left_id, wide_id, Fraction(1), Fraction(1), Fraction(1))
        self.assertEqual(self.risk_counts(), (0, 0))

    def test_invalid_request_rejected(self):
        _, artifact = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        left_id = accept(self.registry, artifact.original)
        _, right = self.risk_station(DOWNSTREAM, 'right', RIGHT_SAMPLE, masses=('1/4', '3/4'))
        right_id = accept(self.registry, right.original)
        self.station.close()
        for request in ((-1, 1, 1), (1, -1, 1), (1, 1, -1), ('x', 1, 1), (True, 1, 1)):
            with self.subTest(request=request):
                with self.assertRaises(RiskSelectionError):
                    publish_risk(self.ledger, left_id, right_id, *request)
        self.assertEqual(self.risk_counts(), (0, 0))

    def test_damaged_v2_rejected(self):
        _, artifact = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        base = json.loads(artifact.original)
        variants = []
        for mutate in (
            lambda wire: wire['body'].__setitem__('masses', ['1/2']),
            lambda wire: wire['body'].__setitem__('masses', ['-1/2', '3/2']),
            lambda wire: wire['body'].__setitem__('masses', ['1/2', '1/2', '0']),
            lambda wire: wire['body'].__setitem__('campaign', ''),
            lambda wire: wire.__setitem__('version', 3),
            lambda wire: wire['body'].pop('campaign'),
            lambda wire: wire['body']['candidates'][0].pop('B'),
        ):
            damaged = json.loads(artifact.original)
            mutate(damaged)
            variants.append(json.dumps(damaged).encode('utf-8'))
        variants.append(b'\xff')
        for damaged in variants:
            with self.subTest(damaged=damaged):
                with self.assertRaises(EvidenceError):
                    accept(self.registry, damaged)
                self.assertEqual(self.intake_count(), 0)

    def test_commit_failure_leaves_no_trace(self):
        _, left = self.risk_station(UPSTREAM, 'left', LEFT_SAMPLE)
        _, right = self.risk_station(DOWNSTREAM, 'right', RIGHT_SAMPLE, masses=('1/4', '3/4'))
        left_id = accept(self.registry, left.original)
        right_id = accept(self.registry, right.original)
        self.station.close()
        existing = publish_risk(self.ledger, left_id, right_id, Fraction(5, 4), Fraction(1), Fraction(1))
        attempted = existing.snapshot.report_number + 1
        self.install_risk_failed_commit()
        with self.assertRaises(RiskPublishError):
            publish_risk(self.ledger, left_id, right_id, Fraction(1), Fraction(1), Fraction(1))
        self.assertFalse(self.center.in_transaction)
        self.center.close()
        self.open_center()
        self.assertEqual(self.risk_counts(), (1, 1))
        self.assertEqual(read_risk(self.ledger, existing.snapshot.report_number), existing)
        with self.assertRaises(ReportNotFound):
            read_risk(self.ledger, attempted)
        retried = publish_risk(self.ledger, left_id, right_id, Fraction(1), Fraction(1), Fraction(1))
        self.assertEqual(self.risk_counts(), (2, 2))
        self.assertEqual(retried.snapshot.outcome.status, 'inconsistent')
        self.assertEqual(read_risk(self.ledger, retried.snapshot.report_number), retried)
        # V1 report/read keep working alongside V2.
        self.open_station()
        v1_first = self.intake_order(UPSTREAM, always_order([('0', '1')]))
        v1_second = self.intake_order(DOWNSTREAM, always_order([('1', '2')]))
        self.station.close()
        v1_report = publish(self.ledger, v1_first, v1_second)
        self.assertEqual(v1_report.receipt.receipt_id, 'R-1')
        self.assertEqual(self.published_counts(), (1, 1))
        self.assertEqual(self.risk_counts(), (2, 2))

    def install_risk_failed_commit(self):
        self.center.executescript('''
            CREATE TEMP TABLE risk_fault_parent (id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE risk_fault_child (
                report_number INTEGER REFERENCES risk_fault_parent (id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TEMP TRIGGER reject_risk_receipt AFTER INSERT ON main.risk_receipts
            BEGIN
                INSERT INTO risk_fault_child VALUES (NEW.report_number);
            END;
        ''')

    def test_reopen_returns_saved_ranges_exactly(self):
        (left_number, right_number, left, right), (left_id, right_id) = self.sample_pair()
        self.station.close()
        published = publish_risk(self.ledger, left_id, right_id, Fraction(5, 4), Fraction(1), Fraction(1))
        self.center.close()
        self.open_center()
        restored = read_risk(self.ledger, published.snapshot.report_number)
        self.assertEqual(restored, published)
        self.assertEqual(restored.snapshot.request.mean0, Fraction(5, 4))
        self.assertEqual(restored.snapshot.request.observed0, Fraction(1))
        self.assertEqual(restored.snapshot.request.gap, Fraction(1))
        self.assertEqual(restored.snapshot.outcome.support, ProbabilityRange(Fraction(1, 4), Fraction(3, 4)))
        self.assertEqual(restored.snapshot.outcome.conditional, ProbabilityRange(Fraction(2, 3), Fraction(1)))
        self.assertEqual([parent.received_id for parent in restored.snapshot.parents], [left_id, right_id])
        self.assertEqual(restored.receipt.receipt_id, 'R-1')
        with self.assertRaises(ReportNotFound):
            read_risk(self.ledger, 99)
