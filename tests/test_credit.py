import json

from demo import (
    DOWNSTREAM, UPSTREAM, a_only_order, always_order, credit_values, sample_order,
    sample_rule, two_candidate_order,
)
from issue.conditions import REPAIR_CHOICES
from receive.registry import accept
from reports.history import read
from reports.publish import publish
from tests.support import ExerciseCase, ranges, scenario


class CreditTests(ExerciseCase):
    def test_fixed_configuration_credit(self):
        coupled = self.freeze_order(UPSTREAM, two_candidate_order(correlated=True))
        exclusive = self.freeze_order(UPSTREAM, two_candidate_order(correlated=False))
        coupled_id = accept(self.registry, coupled.original)
        exclusive_id = accept(self.registry, exclusive.original)
        down = self.intake_order(DOWNSTREAM, always_order([('0', '1')]))
        self.station.close()
        fixed = publish(self.ledger, coupled_id, down)
        variable = publish(self.ledger, exclusive_id, down)
        self.assertEqual(fixed.snapshot.credits, ranges('1/2', '1/2', '1/2', '1/2'))
        self.assertEqual(variable.snapshot.credits, ranges(0, 1, 0, 1))
        self.assertEqual(fixed.snapshot.parents, tuple(self.registry.load(i).source for i in (coupled_id, down)))
        self.assertEqual(variable.snapshot.parents, tuple(self.registry.load(i).source for i in (exclusive_id, down)))
        for report in (fixed, variable):
            self.assertEqual(read(self.ledger, report.snapshot.report_number), report)
        expected = [[['1/2', '1/2'], ['1/2', '1/2']], [['0', '1'], ['0', '1']]]
        scenario(
            'v5', {'and_or': [[0, 0, 0, 1], [0, 1, 1, 1]], 'only_a_or_b': [[0, 1, 0, 1], [0, 0, 1, 1]]},
            expected, [credit_values(fixed), credit_values(variable)],
            [[coupled_id, down], [exclusive_id, down]],
            [[parent.received_id for parent in report.snapshot.parents] for report in (fixed, variable)],
            ['issue/evidence.py', 'analysis/configurations.py', 'analysis/evaluate.py', 'reports/ledger.py'],
            '且和或中每项各有一次一小时边际与一次零边际。仅甲与仅乙分别把一小时全归给对应项。',
        )

    def test_marginal_equivalence(self):
        coupled = self.freeze_order(UPSTREAM, two_candidate_order(correlated=True))
        exclusive = self.freeze_order(UPSTREAM, two_candidate_order(correlated=False))
        first_rows = json.loads(coupled.original)['body']['candidates']
        second_rows = json.loads(exclusive.original)['body']['candidates']
        self.assertNotEqual(first_rows, second_rows)
        for choice in REPAIR_CHOICES:
            with self.subTest(choice=choice):
                possible_first = {tuple(map(tuple, row[choice])) for row in first_rows}
                possible_second = {tuple(map(tuple, row[choice])) for row in second_rows}
                self.assertEqual(possible_first, possible_second)
                expected = {()} if choice == 'none' else {(('0', '1'),)}
                if choice in ('A', 'B'):
                    expected.add(())
                self.assertEqual(possible_first, expected)

    def test_two_orders(self):
        order = sample_order('joint-repair', [sample_rule('joint', ('AB',), [('0', '1')])])
        upstream = self.intake_order(UPSTREAM, order)
        downstream = self.intake_order(DOWNSTREAM, always_order([('0', '1')]))
        self.station.close()
        report = publish(self.ledger, upstream, downstream)
        self.assertEqual(report.snapshot.credits, ranges('1/2', '1/2', '1/2', '1/2'))

    def test_independent_pairs(self):
        def distinct_windows(order_id, choices, windows):
            return sample_order(order_id, [
                sample_rule('early', choices, [windows[0]], requires=['early']),
                sample_rule('late', choices, [windows[1]], requires=['late']),
            ], devices=['early', 'late'], candidates=[('first', ['early']), ('second', ['late'])])

        upstream = self.intake_order(UPSTREAM, distinct_windows('source', ('A', 'AB'), [('0', '1'), ('1', '2')]))
        downstream = self.intake_order(DOWNSTREAM, distinct_windows('sink', REPAIR_CHOICES, [('1', '2'), ('0', '1')]))
        self.station.close()
        report = publish(self.ledger, upstream, downstream)
        # Equal positions yield zero overlap. Both cross positions yield one hour.
        self.assertEqual(report.snapshot.credits, ranges(0, 1, 0, 0))

    def test_shift_overlap(self):
        cases = [(('1', '2'), '0'), (('1/2', '3/2'), '1/2'), (('0', '1'), '1')]
        up = self.intake_order(UPSTREAM, a_only_order([('0', '1')]))
        down_ids = [self.intake_order(DOWNSTREAM, always_order([window])) for window, _ in cases]
        self.station.close()
        actual = []
        archived = []
        expected = []
        for down_id, (window, hours) in zip(down_ids, cases, strict=True):
            with self.subTest(window=window):
                report = publish(self.ledger, up, down_id)
                self.assertEqual(report.snapshot.credits, ranges(hours, hours, 0, 0))
                restored = read(self.ledger, report.snapshot.report_number)
                self.assertEqual(restored, report)
                actual.append(credit_values(report))
                archived.append(credit_values(restored))
                expected.append([[hours, hours], ['0', '0']])
        scenario(
            'v6', {'upstream_A': ['0', '1'], 'downstream': [window for window, _ in cases]},
            expected, actual, expected, archived,
            ['analysis/overlap.py', 'analysis/credit.py', 'reports/history.py'],
            '三个几何交集分别为空、[1/2,1) 和 [0,1)，乙一直没有边际贡献。',
        )

    def test_fragmented_overlap(self):
        upstream = self.intake_order(UPSTREAM, a_only_order([('0', '2')]))
        downstream = self.intake_order(DOWNSTREAM, always_order([('0', '1/2'), ('1', '3/2')]))
        self.station.close()
        report = publish(self.ledger, upstream, downstream)
        self.assertEqual(report.snapshot.credits, ranges(1, 1, 0, 0))

    def test_fragmented_overlap_in_both_orders(self):
        order = sample_order('joint-repair', [sample_rule('joint', ('AB',), [('0', '2')])])
        upstream = self.intake_order(UPSTREAM, order)
        downstream = self.intake_order(DOWNSTREAM, always_order([('0', '1/2'), ('1', '3/2')]))
        self.station.close()
        report = publish(self.ledger, upstream, downstream)
        self.assertEqual(report.snapshot.credits, ranges('1/2', '1/2', '1/2', '1/2'))
