import sqlite3

from analysis.evaluate import evaluate
from receive.registry import EvidenceRegistry
from receive.selection import select_pair
from reports.ledger import PublishedReport, ReportLedger


class PublishError(RuntimeError):
    pass


def publish(ledger: ReportLedger, first_received_id: int, second_received_id: int) -> PublishedReport:
    registry = EvidenceRegistry(ledger.connection)
    try:
        selection = select_pair(registry, first_received_id, second_received_id)
        credits = evaluate(selection)
        return ledger.commit_report(selection.parents, credits)
    except sqlite3.Error as error:
        raise PublishError('复产报告签存失败') from error
