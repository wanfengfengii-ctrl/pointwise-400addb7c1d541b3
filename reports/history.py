from reports.ledger import PublishedReport, PublishedRiskReport, ReportLedger


class ReportNotFound(LookupError):
    pass


def read(ledger: ReportLedger, report_number: int) -> PublishedReport:
    published = ledger.load_published(report_number)
    if published is None:
        raise ReportNotFound(report_number)
    return published


def read_risk(ledger: ReportLedger, report_number: int) -> PublishedRiskReport:
    published = ledger.load_risk(report_number)
    if published is None:
        raise ReportNotFound(report_number)
    return published
