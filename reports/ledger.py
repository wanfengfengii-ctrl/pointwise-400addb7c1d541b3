import sqlite3
from dataclasses import dataclass

from analysis.bounds import CreditRanges
from analysis.risk import RiskOutcome
from receive.provenance import ReceivedSource
from reports.format import ReportSnapshot, decode_report, encode_report
from reports.receipts import (
    SuccessReceipt,
    create_success_receipt,
    decode_success_receipt,
    encode_success_receipt,
)
from reports.risk_format import RiskReportSnapshot, RiskRequest, decode_risk, encode_risk
from storage import is_record_number, write_transaction


@dataclass(frozen=True)
class PublishedReport:
    snapshot: ReportSnapshot
    receipt: SuccessReceipt


@dataclass(frozen=True)
class PublishedRiskReport:
    snapshot: RiskReportSnapshot
    receipt: SuccessReceipt


class ReportLedger:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    report_number INTEGER PRIMARY KEY,
                    first_received_id INTEGER NOT NULL REFERENCES received_evidence (received_id),
                    second_received_id INTEGER NOT NULL REFERENCES received_evidence (received_id),
                    snapshot TEXT NOT NULL,
                    CHECK (first_received_id <> second_received_id)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS success_receipts (
                    report_number INTEGER PRIMARY KEY REFERENCES reports (report_number),
                    receipt_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS risk_reports (
                    report_number INTEGER PRIMARY KEY,
                    first_received_id INTEGER NOT NULL REFERENCES received_evidence (received_id),
                    second_received_id INTEGER NOT NULL REFERENCES received_evidence (received_id),
                    snapshot TEXT NOT NULL,
                    CHECK (first_received_id <> second_received_id)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS risk_receipts (
                    report_number INTEGER PRIMARY KEY REFERENCES risk_reports (report_number),
                    receipt_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL
                )
            ''')

    def commit_report(
        self, parents: tuple[ReceivedSource, ReceivedSource], credits: CreditRanges
    ) -> PublishedReport:
        first, second = parents
        with write_transaction(self.connection):
            (report_number,) = self.connection.execute('''
                SELECT COALESCE(MAX(report_number), 0) + 1 FROM reports
            ''').fetchone()
            snapshot = ReportSnapshot(report_number, parents, credits)
            self.connection.execute('''
                INSERT INTO reports (report_number, first_received_id, second_received_id, snapshot)
                VALUES (?, ?, ?, ?)
            ''', (report_number, first.received_id, second.received_id, encode_report(snapshot)))
            receipt = create_success_receipt(report_number)
            self.connection.execute('''
                INSERT INTO success_receipts (report_number, receipt_id, content) VALUES (?, ?, ?)
            ''', (report_number, receipt.receipt_id, encode_success_receipt(receipt)))
        return PublishedReport(snapshot, receipt)

    def load_published(self, report_number: int) -> PublishedReport | None:
        if not is_record_number(report_number):
            return None
        row = self.connection.execute('''
            SELECT reports.snapshot, success_receipts.content
              FROM reports JOIN success_receipts USING (report_number)
             WHERE reports.report_number = ?
        ''', (report_number,)).fetchone()
        if row is None:
            return None
        return PublishedReport(decode_report(row[0]), decode_success_receipt(row[1]))

    def commit_risk(
        self,
        parents: tuple[ReceivedSource, ReceivedSource],
        version: int,
        campaign: str,
        request: RiskRequest,
        outcome: RiskOutcome,
    ) -> PublishedRiskReport:
        first, second = parents
        with write_transaction(self.connection):
            (report_number,) = self.connection.execute('''
                SELECT COALESCE(MAX(report_number), 0) + 1 FROM risk_reports
            ''').fetchone()
            snapshot = RiskReportSnapshot(
                report_number, version, campaign, request, parents, outcome
            )
            self.connection.execute('''
                INSERT INTO risk_reports
                    (report_number, first_received_id, second_received_id, snapshot)
                VALUES (?, ?, ?, ?)
            ''', (report_number, first.received_id, second.received_id, encode_risk(snapshot)))
            receipt = create_success_receipt(report_number)
            self.connection.execute('''
                INSERT INTO risk_receipts (report_number, receipt_id, content)
                VALUES (?, ?, ?)
            ''', (report_number, receipt.receipt_id, encode_success_receipt(receipt)))
        return PublishedRiskReport(snapshot, receipt)

    def load_risk(self, report_number: int) -> PublishedRiskReport | None:
        if not is_record_number(report_number):
            return None
        row = self.connection.execute('''
            SELECT risk_reports.snapshot, risk_receipts.content
              FROM risk_reports JOIN risk_receipts USING (report_number)
             WHERE risk_reports.report_number = ?
        ''', (report_number,)).fetchone()
        if row is None:
            return None
        return PublishedRiskReport(decode_risk(row[0]), decode_success_receipt(row[1]))
