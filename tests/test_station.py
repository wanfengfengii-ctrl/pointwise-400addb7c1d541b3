import json

from demo import SHIFT, UPSTREAM, a_only_order, sample_order, sample_rule
from issue.evidence import freeze
from receive.registry import accept
from station.corrections import correct
from station.revisions import RevisionNotFound
from station.workorders import WorkorderError, record
from tests.support import ExerciseCase, scenario


class StationTests(ExerciseCase):
    def test_freeze_revision(self):
        raw = sample_order('private-workorder', [
            sample_rule('private-window', ('A', 'AB'), [('0', '1')], requires=['private-device']),
        ], devices=['private-device'], candidates=[('private-candidate', ['private-device'])])
        original = record(self.revisions, UPSTREAM, SHIFT, raw)
        amended = correct(self.revisions, UPSTREAM, original, [
            {'rule_id': 'private-window', 'window_index': 0, 'window': ['1', '2']},
        ])
        evidence = freeze(self.issues, UPSTREAM, original)
        newer = freeze(self.issues, UPSTREAM, amended)
        wire = json.loads(evidence.original)
        expected = {'none': [], 'A': [['0', '1']], 'B': [], 'AB': [['0', '1']]}
        actual = wire['body']['candidates'][0]
        self.assertEqual(actual, expected)
        self.assertEqual(wire['version'], 1)
        self.assertEqual(wire['issue_id'], evidence.issue_id)
        self.assertEqual(wire['station'], UPSTREAM)
        self.assertNotIn(b'private-', evidence.original)
        self.assertNotEqual(newer.issue_id, evidence.issue_id)
        self.assertEqual(json.loads(newer.original)['body']['candidates'][0]['A'], [['1', '2']])
        self.assertEqual(self.revisions.get(UPSTREAM, original).order, raw)
        self.assertEqual(self.revisions.get(UPSTREAM, amended).parent_number, original)
        received_id = accept(self.registry, evidence.original)
        received = self.registry.load(received_id)
        self.assertEqual(received.envelope.original, evidence.original)
        self.assertEqual(received.source.issue_id, evidence.issue_id)
        scenario(
            'v1', {'shift': ['0', '2'], 'original_A': ['0', '1'], 'amended_A': ['1', '2']},
            expected, actual, True, received.envelope.original == evidence.original,
            ['station/workorders.py', 'issue/evidence.py', 'receive/registry.py'],
            '原修订仅在包含甲的两种选择下开放第一小时，中心收到同一原件。',
        )

    def test_complete_responses(self):
        order = sample_order('private-order', [
            sample_rule('private-heat-rule', ('A', 'AB'), [('1/2', '1'), ('0', '3/4')], requires=['private-heat']),
            sample_rule('private-tail', ('AB',), [('1', '3/2')]),
        ], devices=['private-heat'], candidates=[('hot', ['private-heat']), ('cold', [])])
        artifact = self.freeze_order(UPSTREAM, order)
        self.assertEqual(json.loads(artifact.original)['body']['candidates'], [
            {'none': [], 'A': [['0', '1']], 'B': [], 'AB': [['0', '3/2']]},
            {'none': [], 'A': [], 'B': [], 'AB': [['1', '3/2']]},
        ])

    def test_freeze_retry(self):
        number = record(self.revisions, UPSTREAM, SHIFT, a_only_order([('0', '1')]))
        original = freeze(self.issues, UPSTREAM, number)
        self.station.close()
        self.open_station()
        retry = freeze(self.issues, UPSTREAM, number)
        self.assertEqual(retry, original)
        self.assertEqual(self.station_counts(), (1, 1))

    def test_unknown_revision(self):
        number = record(self.revisions, UPSTREAM, SHIFT, a_only_order([('0', '1')]))
        for station, revision in [('another-station', number), (UPSTREAM, number + 1)]:
            with self.subTest(station=station, revision=revision):
                with self.assertRaises(RevisionNotFound):
                    freeze(self.issues, station, revision)
        self.assertEqual(self.station_counts(), (1, 0))

    def test_reject_invalid_window(self):
        valid = record(self.revisions, UPSTREAM, SHIFT, a_only_order([('0', '1')]))
        for window in [('3/2', '1/2'), ('1', '1'), ('1', '5/2'), ('1/0', '2'), (False, '1')]:
            with self.subTest(window=window):
                order = sample_order('invalid-order', [
                    sample_rule('good', ('A',), [('0', '1')]),
                    sample_rule('dormant', ('AB',), [window], requires=['off']),
                ], devices=['off'])
                with self.assertRaises(WorkorderError):
                    record(self.revisions, UPSTREAM, SHIFT, order)
                self.assertEqual(self.station_counts(), (1, 0))
        retained = self.revisions.get(UPSTREAM, valid).order
        self.assertEqual(retained['rules'][0]['windows'], [['0', '1']])
        scenario(
            'v2', {'dormant_reverse_window': ['3/2', '1/2']}, [1, 0], list(self.station_counts()),
            [['0', '1']], retained['rules'][0]['windows'],
            ['station/windows.py', 'station/workorders.py', 'station/revisions.py'],
            '反向窗的末端早于起点，既有修订的原窗仍为 [0,1)。',
        )

    def test_reject_invalid_candidate(self):
        rules = [sample_rule('run', ('A',), [('0', '1')])]
        for candidates in ([], [('bad', ['undeclared'])], [('repeat', []), ('repeat', [])], [(str(i), []) for i in range(5)]):
            with self.subTest(candidates=candidates):
                with self.assertRaises(WorkorderError):
                    record(self.revisions, UPSTREAM, SHIFT, sample_order('bad', rules, candidates=candidates))
        self.assertEqual(self.station_counts(), (0, 0))
