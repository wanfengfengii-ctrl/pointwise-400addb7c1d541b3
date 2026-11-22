import json
import sqlite3
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from issue.catalog import IssueCatalog
from issue.conditions import REPAIR_CHOICES
from issue.evidence import freeze
from receive.registry import EvidenceRegistry, accept
from reports.history import read
from reports.ledger import PublishedReport, ReportLedger
from reports.publish import publish
from station.corrections import correct
from station.revisions import RevisionStore
from station.shifts import Shift
from station.workorders import record


SHIFT = Shift('trial-day', Fraction(0), Fraction(2))
UPSTREAM = 'upstream'
DOWNSTREAM = 'downstream'


def sample_rule(rule_id, choices, windows, *, requires=()):
    return {
        'id': rule_id,
        'choices': list(choices),
        'windows': [list(window) for window in windows],
        'requires': list(requires),
    }


def sample_order(order_id, rules, *, devices=(), candidates=None):
    if candidates is None:
        candidates = [('private-normal', ())]
    return {
        'workorder_id': order_id,
        'devices': list(devices),
        'candidates': [{'id': name, 'enabled': list(enabled)} for name, enabled in candidates],
        'rules': list(rules),
    }


def a_only_order(windows):
    return sample_order('private-up-order', [sample_rule('run', ('A', 'AB'), windows)])


def always_order(windows):
    return sample_order('private-down-order', [sample_rule('run', REPAIR_CHOICES, windows)])


def two_candidate_order(*, correlated):
    conditions = ('private-condition-1', 'private-condition-2')
    choices = (('AB',), ('A', 'B', 'AB')) if correlated else (('A', 'AB'), ('B', 'AB'))
    return sample_order(
        'private-candidate-order',
        [
            sample_rule(f'private-rule-{index}', choice, [('0', '1')], requires=[condition])
            for index, (choice, condition) in enumerate(zip(choices, conditions, strict=True))
        ],
        devices=conditions,
        candidates=[(f'private-configuration-{index}', (condition,)) for index, condition in enumerate(conditions)],
    )


def credit_values(report: PublishedReport) -> list[list[str]]:
    result = report.snapshot.credits
    return [[str(bounds.minimum), str(bounds.maximum)] for bounds in (result.a, result.b)]


def main() -> None:
    with TemporaryDirectory(prefix='restart-drill-') as directory:
        station_path = Path(directory) / 'station.sqlite3'
        center_path = Path(directory) / 'center.sqlite3'
        with closing(sqlite3.connect(center_path)) as center:
            registry, ledger = EvidenceRegistry(center), ReportLedger(center)
            registry.initialize()
            ledger.initialize()
            with closing(sqlite3.connect(station_path)) as station:
                store, catalog = RevisionStore(station), IssueCatalog(station)
                store.initialize()
                catalog.initialize()
                upstream = record(store, UPSTREAM, SHIFT, a_only_order([('0', '1')]))
                downstream = record(store, DOWNSTREAM, SHIFT, always_order([('1', '2')]))
                first = accept(registry, freeze(catalog, UPSTREAM, upstream).original)
                second = accept(registry, freeze(catalog, DOWNSTREAM, downstream).original)
            original = publish(ledger, first, second)
            with closing(sqlite3.connect(station_path)) as station:
                store, catalog = RevisionStore(station), IssueCatalog(station)
                amendment = correct(store, DOWNSTREAM, downstream, [
                    {'rule_id': 'run', 'window_index': 0, 'window': ['1/2', '3/2']},
                ])
                third = accept(registry, freeze(catalog, DOWNSTREAM, amendment).original)
            amended = publish(ledger, first, third)
        with closing(sqlite3.connect(center_path)) as reopened:
            history = ReportLedger(reopened)
            restored = [read(history, report.snapshot.report_number) for report in (original, amended)]
        expected = [[['0', '0'], ['0', '0']], [['1/2', '1/2'], ['0', '0']]]
        actual = [credit_values(report) for report in (original, amended)]
        downstream_expected = [
            {'credits': expected[0], 'parents': [first, second], 'report': 1, 'receipt': 'R-1'},
            {'credits': expected[1], 'parents': [first, third], 'report': 2, 'receipt': 'R-2'},
        ]
        downstream_actual = [
            {
                'credits': credit_values(report),
                'parents': [source.received_id for source in report.snapshot.parents],
                'report': report.snapshot.report_number,
                'receipt': report.receipt.receipt_id,
            }
            for report in restored
        ]
        assert actual == expected, actual
        assert restored == [original, amended], restored
        assert downstream_actual == downstream_expected, downstream_actual
        scenario = {
            'case_id': 'v7',
            'input': {'shift': ['0', '2'], 'upstream_A': ['0', '1'], 'downstream': [['1', '2'], ['1/2', '3/2']]},
            'expected': expected,
            'actual': actual,
            'downstream_expected': downstream_expected,
            'downstream_actual': downstream_actual,
            'code_paths': ['station/corrections.py', 'issue/evidence.py', 'analysis/evaluate.py', 'reports/history.py'],
            'oracle': '手算交集长度为零与半小时，乙对任何选择均无影响，按签发顺序复领两件定稿。',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
