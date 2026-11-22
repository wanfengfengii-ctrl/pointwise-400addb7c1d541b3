from copy import deepcopy

from station.revisions import RevisionStore
from station.workorders import WorkorderError, validate_workorder


def apply_correction(order: dict, changes: object) -> dict:
    if not isinstance(changes, list) or not changes:
        raise WorkorderError('勘误须指定至少一个现有时段')
    corrected = deepcopy(order)
    rules = {rule['id']: rule for rule in corrected['rules']}
    touched = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'rule_id', 'window_index', 'window'}:
            raise WorkorderError('勘误字段须为 rule_id、window_index、window')
        rule_id = change['rule_id']
        if not isinstance(rule_id, str) or rule_id not in rules:
            raise WorkorderError(f'未知规则 {rule_id!r}')
        windows = rules[rule_id]['windows']
        index = change['window_index']
        if type(index) is not int or not 0 <= index < len(windows):
            raise WorkorderError(f'规则 {rule_id} 的时段下标越界')
        target = (rule_id, index)
        if target in touched:
            raise WorkorderError(f'重复勘误规则 {rule_id} 的第 {index} 个时段')
        windows[index] = change['window']
        touched.add(target)
    return corrected


def correct(store: RevisionStore, station: str, revision_number: int, changes: object) -> int:
    prior = store.get(station, revision_number)
    corrected = apply_correction(prior.order, changes)
    return store.append(
        prior.station, prior.shift, validate_workorder(prior.shift, corrected), prior.number
    )
