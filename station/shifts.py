from dataclasses import dataclass
from fractions import Fraction

from station.windows import Window, parse_hour, validate_window


@dataclass(frozen=True)
class Shift:
    shift_id: str
    start: Fraction
    end: Fraction


def validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or '\x00' in value:
        raise ValueError(f'{label}须为首尾无空白的非空标识')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(f'{label}须可用 UTF-8 表示') from error
    return value


def validate_shift(value: object) -> Shift:
    if not isinstance(value, Shift):
        raise ValueError('班次须为 Shift')
    shift_id = validate_identifier(value.shift_id, '班次')
    start, end = parse_hour(value.start), parse_hour(value.end)
    if start >= end:
        raise ValueError('班次须有正长度')
    return Shift(shift_id, start, end)


def check_window_in_shift(value: object, shift: Shift) -> Window:
    window = validate_window(value)
    if window.start < shift.start or window.end > shift.end:
        raise ValueError('时段越出班次坐标')
    return window


def encode_shift(shift: Shift) -> dict[str, str]:
    return {'id': shift.shift_id, 'start': str(shift.start), 'end': str(shift.end)}


def decode_shift(value: object) -> Shift:
    if not isinstance(value, dict) or set(value) != {'id', 'start', 'end'}:
        raise ValueError('班次字段须包含 id、start、end')
    if not all(isinstance(part, str) for part in value.values()):
        raise ValueError('班次字段须为文本')
    return validate_shift(Shift(value['id'], parse_hour(value['start']), parse_hour(value['end'])))
