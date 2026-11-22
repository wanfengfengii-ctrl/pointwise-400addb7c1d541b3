from fractions import Fraction
from typing import Iterator, Sequence

from station.windows import Window


def intersect_windows(first: Sequence[Window], second: Sequence[Window]) -> Iterator[Window]:
    left_index = right_index = 0
    while left_index < len(first) and right_index < len(second):
        left, right = first[left_index], second[right_index]
        start, end = max(left.start, right.start), min(left.end, right.end)
        if start < end:
            yield Window(start, end)
        if left.end <= right.end:
            left_index += 1
        if right.end <= left.end:
            right_index += 1


def common_hours(first: Sequence[Window], second: Sequence[Window]) -> Fraction:
    return sum((part.end - part.start for part in intersect_windows(first, second)), Fraction(0))
