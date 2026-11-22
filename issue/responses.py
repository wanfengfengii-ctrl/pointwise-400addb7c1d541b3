from dataclasses import dataclass

from issue.conditions import REPAIR_CHOICES
from station.shifts import Shift, check_window_in_shift
from station.windows import Window, union_windows


@dataclass(frozen=True)
class CandidateResponse:
    by_choice: tuple[tuple[Window, ...], ...]


def encode_responses(candidates: tuple[CandidateResponse, ...]) -> dict:
    return {
        'candidates': [
            {
                choice: [[str(window.start), str(window.end)] for window in windows]
                for choice, windows in zip(REPAIR_CHOICES, response.by_choice, strict=True)
            }
            for response in candidates
        ]
    }


def _decode_windows(value: object, shift: Shift) -> tuple[Window, ...]:
    if not isinstance(value, list):
        raise ValueError('每种检修响应须为时段列表')
    windows = []
    for raw_window in value:
        if (
            not isinstance(raw_window, list)
            or len(raw_window) != 2
            or not all(isinstance(endpoint, str) for endpoint in raw_window)
        ):
            raise ValueError('站件时段须含两个有理数字符串端点')
        windows.append(check_window_in_shift(raw_window, shift))
    return union_windows(windows)


def decode_responses(body: object, shift: Shift) -> tuple[CandidateResponse, ...]:
    if not isinstance(body, dict) or set(body) != {'candidates'}:
        raise ValueError('站件正文须包含候选列表')
    candidates = body['candidates']
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 4:
        raise ValueError('站件须有一至四个匿名候选')
    responses = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != set(REPAIR_CHOICES):
            raise ValueError('每个匿名候选须包含四种检修响应')
        responses.append(CandidateResponse(tuple(
            _decode_windows(candidate[choice], shift) for choice in REPAIR_CHOICES
        )))
    return tuple(responses)
