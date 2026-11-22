from issue.conditions import rule_applies
from station.windows import Window, union_windows, validate_window


def available_windows(order: dict, candidate: dict, choice: str) -> tuple[Window, ...]:
    enabled = frozenset(candidate['enabled'])
    active_windows = (
        validate_window(raw_window)
        for rule in order['rules']
        if rule_applies(rule, enabled, choice)
        for raw_window in rule['windows']
    )
    return union_windows(active_windows)
