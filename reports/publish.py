import sqlite3
from fractions import Fraction

from analysis.evaluate import evaluate
from analysis.risk import compute_risk
from receive.registry import EvidenceRegistry
from receive.risk_selection import RiskSelectionError, select_risk_pair
from receive.selection import select_pair
from reports.ledger import PublishedReport, PublishedRiskReport, ReportLedger
from reports.risk_format import RiskRequest
from station.windows import parse_hour


class PublishError(RuntimeError):
    pass


class RiskPublishError(RuntimeError):
    pass


def publish(ledger: ReportLedger, first_received_id: int, second_received_id: int) -> PublishedReport:
    registry = EvidenceRegistry(ledger.connection)
    try:
        selection = select_pair(registry, first_received_id, second_received_id)
        credits = evaluate(selection)
        return ledger.commit_report(selection.parents, credits)
    except sqlite3.Error as error:
        raise PublishError('复产报告签存失败') from error


def _risk_hours(value: object, label: str) -> Fraction:
    try:
        hours = parse_hour(value)
    except ValueError as error:
        raise RiskSelectionError(f'{label} 须为非负有理小时数') from error
    if hours < 0:
        raise RiskSelectionError(f'{label} 须为非负有理小时数')
    return hours


def publish_risk(
    ledger: ReportLedger,
    first_received_id: int,
    second_received_id: int,
    mean0,
    observed0,
    gap,
) -> PublishedRiskReport:
    request = RiskRequest(
        _risk_hours(mean0, 'mean0'), _risk_hours(observed0, 'observed0'), _risk_hours(gap, 'gap')
    )
    registry = EvidenceRegistry(ledger.connection)
    try:
        selection = select_risk_pair(registry, first_received_id, second_received_id)
        outcome = compute_risk(
            selection.first, selection.second,
            request.mean0, request.observed0, request.gap,
        )
        return ledger.commit_risk(selection.parents, 2, selection.first.campaign, request, outcome)
    except sqlite3.Error as error:
        raise RiskPublishError('实测工况风险签存失败') from error
