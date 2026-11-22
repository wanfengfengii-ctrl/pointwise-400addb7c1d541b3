from dataclasses import dataclass

from receive.envelope import EvidenceError, ValidatedEnvelope
from receive.provenance import ReceivedSource
from receive.registry import EvidenceNotFound, EvidenceRegistry


class RiskSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class SelectedRiskPair:
    first: ValidatedEnvelope
    second: ValidatedEnvelope
    parents: tuple[ReceivedSource, ReceivedSource]


def _load_selected(
    registry: EvidenceRegistry, received_id: int
) -> tuple[ValidatedEnvelope, ReceivedSource]:
    if type(received_id) is not int or received_id <= 0:
        raise RiskSelectionError(f'缺少指定实收件 {received_id!r}')
    try:
        received = registry.load(received_id)
    except EvidenceNotFound as error:
        raise RiskSelectionError(f'缺少指定实收件 {error.args[0]!r}') from error
    except EvidenceError as error:
        raise RiskSelectionError(str(error)) from error
    if received.envelope.version != 2:
        raise RiskSelectionError('风险签报只接受 V2 站件')
    return received.envelope, received.source


def select_risk_pair(
    registry: EvidenceRegistry, first_received_id: int, second_received_id: int
) -> SelectedRiskPair:
    first, first_source = _load_selected(registry, first_received_id)
    second, second_source = _load_selected(registry, second_received_id)
    if first.station == second.station:
        raise RiskSelectionError('须选择两个不同站点的 V2 站件')
    if first.shift != second.shift:
        raise RiskSelectionError('两个 V2 站件须有相同班次标识与坐标')
    if first.campaign != second.campaign:
        raise RiskSelectionError('两个 V2 站件须属于同一巡检批次')
    return SelectedRiskPair(first, second, (first_source, second_source))
