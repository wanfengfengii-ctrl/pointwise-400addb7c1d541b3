import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SuccessReceipt:
    report_number: int
    receipt_id: str


def create_success_receipt(report_number: int) -> SuccessReceipt:
    return SuccessReceipt(report_number, f'R-{report_number}')


def encode_success_receipt(receipt: SuccessReceipt) -> str:
    return json.dumps({
        'report_number': receipt.report_number,
        'receipt_id': receipt.receipt_id,
    }, separators=(',', ':'))


def decode_success_receipt(content: str) -> SuccessReceipt:
    data = json.loads(content)
    return SuccessReceipt(data['report_number'], data['receipt_id'])
