from dataclasses import dataclass

from receive.envelope import EvidenceError
from receive.provenance import ReceivedSource
from receive.registry import EvidenceNotFound, EvidenceRegistry, ReceivedEvidence


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class SelectedEvidencePair:
    first: ReceivedEvidence
    second: ReceivedEvidence

    @property
    def parents(self) -> tuple[ReceivedSource, ReceivedSource]:
        return self.first.source, self.second.source


def select_pair(registry: EvidenceRegistry, first_id: int, second_id: int) -> SelectedEvidencePair:
    try:
        first = registry.load(first_id)
        second = registry.load(second_id)
    except EvidenceNotFound as error:
        raise SelectionError(f'缺少指定实收件 {error.args[0]!r}') from error
    except EvidenceError as error:
        raise SelectionError(str(error)) from error
    if first.source.version != 1 or second.source.version != 1:
        raise SelectionError('V1 复产报告只接受 V1 站件')
    if first.source.station == second.source.station:
        raise SelectionError('须选择两个不同站点的实收件')
    if first.source.shift != second.source.shift:
        raise SelectionError('两个实收件须有相同班次标识和坐标')
    return SelectedEvidencePair(first, second)
