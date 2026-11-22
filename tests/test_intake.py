import hashlib
import json
from copy import deepcopy

from demo import DOWNSTREAM, UPSTREAM, a_only_order, always_order, credit_values
from receive.envelope import EvidenceError
from receive.registry import IntakeConflict, accept
from reports.publish import publish
from tests.support import ExerciseCase, ranges, scenario


class IntakeTests(ExerciseCase):
    def test_conflicting_receipt(self):
        original = self.freeze_order(UPSTREAM, a_only_order([('0', '1')]))
        received_id = accept(self.registry, original.original)
        counterparty = self.intake_order(DOWNSTREAM, always_order([('0', '1')]))
        self.station.close()
        baseline = publish(self.ledger, received_id, counterparty)
        changed = json.loads(original.original)
        response = changed['body']['candidates'][0]
        response['A'] = response['AB'] = [['0', '1/2']]
        with self.assertRaises(IntakeConflict):
            accept(self.registry, json.dumps(changed).encode('utf-8'))
        self.assertEqual(self.intake_count(), 2)
        saved = self.registry.load(received_id)
        self.assertEqual(saved.envelope.original, original.original)
        digest = hashlib.sha256(original.original).hexdigest()
        self.assertEqual(saved.source.fingerprint, digest)
        again = publish(self.ledger, received_id, counterparty)
        self.assertEqual(baseline.snapshot.credits, ranges(1, 1, 0, 0))
        self.assertEqual(again.snapshot.credits, baseline.snapshot.credits)
        self.assertEqual(again.snapshot.parents, baseline.snapshot.parents)
        scenario(
            'v3', {'original_A_hours': '1', 'conflicting_A_hours': '1/2'},
            2, self.intake_count(), [['1', '1'], ['0', '0']], credit_values(again),
            ['receive/envelope.py', 'receive/registry.py', 'reports/publish.py'],
            '同发行号的有效异内容遭拒，原件仍和对站重合一小时。',
        )

    def test_damaged_body(self):
        artifact = self.freeze_order(UPSTREAM, a_only_order([('0', '1')]))
        base = json.loads(artifact.original)
        missing, out_of_shift, wrong_type, no_candidates = [deepcopy(base) for _ in range(4)]
        del missing['body']['candidates'][0]['B']
        out_of_shift['body']['candidates'][0]['A'] = [['0', '3']]
        wrong_type['body']['candidates'][0]['A'] = [[0, 1]]
        no_candidates['body']['candidates'] = []
        originals = [json.dumps(damaged).encode('utf-8') for damaged in (missing, out_of_shift, wrong_type, no_candidates)]
        originals.extend([b'\xff', b'{"version":1,"version":1}'])
        for damaged in originals:
            with self.subTest(damaged=damaged):
                with self.assertRaises(EvidenceError):
                    accept(self.registry, damaged)
                self.assertEqual(self.intake_count(), 0)
        self.assertEqual(accept(self.registry, artifact.original), 1)

    def test_exact_retry(self):
        artifact = self.freeze_order(UPSTREAM, a_only_order([('0', '1')]))
        first = accept(self.registry, artifact.original)
        before = self.registry.load(first)
        self.center.close()
        self.open_center()
        second = accept(self.registry, artifact.original)
        self.assertEqual(first, second)
        self.assertEqual(self.registry.load(second), before)
        self.assertEqual(self.intake_count(), 1)
