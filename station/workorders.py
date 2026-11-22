from issue.conditions import REPAIR_CHOICES
from station.revisions import RevisionStore
from station.shifts import Shift, check_window_in_shift, validate_identifier, validate_shift


class WorkorderError(ValueError):
    pass


def _check_fields(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f'{label}字段须为 {", ".join(sorted(fields))}')
    return value


def _list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f'{label}须为列表')
    return value


def _unique_identifiers(value: object, label: str) -> list[str]:
    identifiers = [validate_identifier(item, label) for item in _list(value, label)]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f'{label}存在重复标识')
    return identifiers


def _check_devices(values: list[str], declared: set[str], label: str) -> None:
    undeclared = set(values) - declared
    if undeclared:
        raise ValueError(f'{label}引用未声明设备 {", ".join(sorted(undeclared))}')


def _validate_candidates(value: object, devices: set[str]) -> list[dict]:
    candidates = _list(value, '候选配置')
    if not 1 <= len(candidates) <= 4:
        raise ValueError('每个工单须有一至四个候选配置')
    result = []
    seen = set()
    for item in candidates:
        candidate = _check_fields(item, {'id', 'enabled'}, '候选')
        candidate_id = validate_identifier(candidate['id'], '候选标识')
        if candidate_id in seen:
            raise ValueError(f'重复候选标识 {candidate_id}')
        enabled = _unique_identifiers(candidate['enabled'], '启用设备')
        _check_devices(enabled, devices, candidate_id)
        result.append({'id': candidate_id, 'enabled': enabled})
        seen.add(candidate_id)
    return result


def _validate_rules(value: object, devices: set[str], shift: Shift) -> list[dict]:
    result = []
    seen = set()
    for item in _list(value, '作业规则'):
        rule = _check_fields(item, {'id', 'requires', 'choices', 'windows'}, '规则')
        rule_id = validate_identifier(rule['id'], '规则标识')
        if rule_id in seen:
            raise ValueError(f'重复规则标识 {rule_id}')
        requires = _unique_identifiers(rule['requires'], '所需设备')
        _check_devices(requires, devices, rule_id)
        choices = _unique_identifiers(rule['choices'], '检修选择')
        if not choices or set(choices) - set(REPAIR_CHOICES):
            raise ValueError(f'规则 {rule_id} 须使用合法的检修选择')
        windows = []
        for raw_window in _list(rule['windows'], '作业时段'):
            window = check_window_in_shift(raw_window, shift)
            windows.append([str(window.start), str(window.end)])
        result.append({'id': rule_id, 'requires': requires, 'choices': choices, 'windows': windows})
        seen.add(rule_id)
    return result


def validate_workorder(shift: Shift, order: object) -> dict:
    try:
        checked_shift = validate_shift(shift)
        data = _check_fields(order, {'workorder_id', 'devices', 'candidates', 'rules'}, '工单')
        order_id = validate_identifier(data['workorder_id'], '工单标识')
        devices = _unique_identifiers(data['devices'], '声明设备')
        return {
            'workorder_id': order_id,
            'devices': devices,
            'candidates': _validate_candidates(data['candidates'], set(devices)),
            'rules': _validate_rules(data['rules'], set(devices), checked_shift),
        }
    except ValueError as error:
        raise WorkorderError(str(error)) from error


def record(store: RevisionStore, station: str, shift: Shift, order: object) -> int:
    try:
        station_id = validate_identifier(station, '站点')
        checked_shift = validate_shift(shift)
    except ValueError as error:
        raise WorkorderError(str(error)) from error
    return store.append(station_id, checked_shift, validate_workorder(checked_shift, order))
