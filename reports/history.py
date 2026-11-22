from reports.ledger import PublishedReport, ReportLedger


class ReportNotFound(LookupError):
    pass


def read(ledger: ReportLedger, report_number: int) -> PublishedReport:
    published = ledger.load_published(report_number)
    if published is None:
        raise ReportNotFound(report_number)
    return published
