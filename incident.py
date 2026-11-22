import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import DOWNSTREAM, SHIFT, UPSTREAM, always_order, credit_values, two_candidate_order
from issue.catalog import IssueCatalog
from issue.evidence import freeze
from receive.registry import EvidenceRegistry, accept
from reports.ledger import ReportLedger
from reports.publish import publish
from station.revisions import RevisionStore
from station.workorders import record


def _display(values: list[list[str]]) -> str:
    return ' '.join(f'{label}=[{lower},{upper}]' for label, (lower, upper) in zip('AB', values, strict=True))


def main() -> int:
    with TemporaryDirectory(prefix='restart-credit-') as directory:
        root = Path(directory)
        with closing(sqlite3.connect(root / 'center.sqlite3')) as center:
            registry, ledger = EvidenceRegistry(center), ReportLedger(center)
            registry.initialize()
            ledger.initialize()
            with closing(sqlite3.connect(root / 'station.sqlite3')) as station:
                revisions, catalog = RevisionStore(station), IssueCatalog(station)
                revisions.initialize()
                catalog.initialize()
                first_revision = record(revisions, UPSTREAM, SHIFT, two_candidate_order(correlated=True))
                second_revision = record(revisions, DOWNSTREAM, SHIFT, always_order([('0', '1')]))
                first_id = accept(registry, freeze(catalog, UPSTREAM, first_revision).original)
                second_id = accept(registry, freeze(catalog, DOWNSTREAM, second_revision).original)
            report = publish(ledger, first_id, second_id)
    actual = credit_values(report)
    expected = [['1/2', '1/2'], ['1/2', '1/2']]
    if actual != expected:
        print(f'REPAIR_CREDIT_WORLD_MIX actual {_display(actual)} expected {_display(expected)}', file=sys.stderr)
        return 1
    print(f'检修收益 {_display(actual)}（小时）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
