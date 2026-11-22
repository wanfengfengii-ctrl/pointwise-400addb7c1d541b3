import json
from dataclasses import dataclass

from issue.availability import available_windows
from issue.catalog import IssueCatalog
from issue.conditions import REPAIR_CHOICES
from issue.responses import CandidateResponse, encode_responses
from station.revisions import RevisionStore
from station.shifts import Shift, encode_shift


@dataclass(frozen=True)
class FrozenEvidence:
    issue_id: str
    station: str
    shift: Shift
    original: bytes


def freeze(catalog: IssueCatalog, station: str, revision_number: int) -> FrozenEvidence:
    revision = RevisionStore(catalog.connection).get(station, revision_number)

    def build_original(issue_id: str) -> bytes:
        responses = tuple(
            CandidateResponse(tuple(
                available_windows(revision.order, candidate, choice) for choice in REPAIR_CHOICES
            ))
            for candidate in revision.order['candidates']
        )
        envelope = {
            'version': 1,
            'issue_id': issue_id,
            'station': revision.station,
            'shift': encode_shift(revision.shift),
            'body': encode_responses(responses),
        }
        return json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    issued = catalog.get_or_issue(revision.station, revision.number, build_original)
    return FrozenEvidence(issued.issue_id, issued.station, revision.shift, issued.original)
