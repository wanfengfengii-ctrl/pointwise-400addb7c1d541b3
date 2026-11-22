from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


@dataclass(frozen=True, order=True)
class Window:
    start: Fraction
    end: Fraction


def parse_hour(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError('小时数须为整数、Fraction 或有理数字符串')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'非法有理小时数 {value!r}') from error


def validate_window(value: object) -> Window:
    if isinstance(value, Window):
        start, end = value.start, value.end
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        start, end = value
    else:
        raise ValueError('时段须有两个端点')
    window = Window(parse_hour(start), parse_hour(end))
    if window.start >= window.end:
        raise ValueError('时段末端须晚于起点')
    return window


def union_windows(windows: Iterable[Window]) -> tuple[Window, ...]:
    merged: list[Window] = []
    for window in sorted(windows):
        if merged and window.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = Window(previous.start, max(previous.end, window.end))
        else:
            merged.append(window)
    return tuple(merged)
