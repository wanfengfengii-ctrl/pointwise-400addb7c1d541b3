from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Sequence

from analysis.credit import compute_pair_credit
from analysis.overlap import common_hours
from issue.responses import CandidateResponse
from receive.envelope import ValidatedEnvelope

STATUS_OK = 'ok'
STATUS_INCONSISTENT = 'inconsistent'
STATUS_UNSUPPORTED = 'unsupported'


@dataclass(frozen=True)
class ProbabilityRange:
    minimum: Fraction
    maximum: Fraction

    @property
    def lower(self) -> Fraction:
        return self.minimum

    @property
    def upper(self) -> Fraction:
        return self.maximum


@dataclass(frozen=True)
class RiskOutcome:
    status: str
    support: ProbabilityRange | None
    conditional: ProbabilityRange | None

    @property
    def support_range(self) -> ProbabilityRange | None:
        return self.support

    @property
    def conditional_range(self) -> ProbabilityRange | None:
        return self.conditional


def _reduce(equations: Sequence[tuple[Sequence[Fraction], Fraction]], size: int):
    """RREF of the joint system. Returns None when the constraints are inconsistent."""
    rows = [[Fraction(value) for value in coefficients] + [Fraction(rhs)]
            for coefficients, rhs in equations]
    pivot_row = 0
    for column in range(size):
        pivot = next((r for r in range(pivot_row, len(rows)) if rows[r][column] != 0), None)
        if pivot is None:
            continue
        rows[pivot_row], rows[pivot] = rows[pivot], rows[pivot_row]
        scale = rows[pivot_row][column]
        rows[pivot_row] = [value / scale for value in rows[pivot_row]]
        for r in range(len(rows)):
            if r != pivot_row and rows[r][column] != 0:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[pivot_row])]
        pivot_row += 1
        if pivot_row == len(rows):
            break
    for row in rows:
        if all(value == 0 for value in row[:size]) and row[size] != 0:
            return None
    return [(rows[r][:size], rows[r][size]) for r in range(pivot_row)]


def _solve_square(matrix: Sequence[Sequence[Fraction]], rhs: Sequence[Fraction]):
    size = len(matrix)
    augmented = [[Fraction(value) for value in matrix[i]] + [Fraction(rhs[i])] for i in range(size)]
    for column in range(size):
        pivot = next((r for r in range(column, size) if augmented[r][column] != 0), None)
        if pivot is None:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for r in range(size):
            if r != column and augmented[r][column] != 0:
                factor = augmented[r][column]
                augmented[r] = [a - factor * b for a, b in zip(augmented[r], augmented[column])]
    return [augmented[i][size] for i in range(size)]


def joint_vertices(
    row_masses: Sequence[Fraction],
    column_masses: Sequence[Fraction],
    costs: Sequence[Sequence[Fraction]],
    mean: Fraction,
) -> tuple[tuple[Fraction, ...], ...] | None:
    """All vertices of {p >= 0 : row sums, column sums and weighted mean hold}.

    Returns None when no non-negative joint masses satisfy the constraints.
    """
    rows, columns = len(row_masses), len(column_masses)
    size = rows * columns
    equations = []
    for i in range(rows):
        coefficients = [Fraction(0)] * size
        for j in range(columns):
            coefficients[i * columns + j] = Fraction(1)
        equations.append((coefficients, row_masses[i]))
    for j in range(columns - 1):
        coefficients = [Fraction(0)] * size
        for i in range(rows):
            coefficients[i * columns + j] = Fraction(1)
        equations.append((coefficients, column_masses[j]))
    coefficients = [costs[i][j] for i in range(rows) for j in range(columns)]
    equations.append((coefficients, mean))

    reduced = _reduce(equations, size)
    if reduced is None:
        return None
    rank = len(reduced)
    vertices = set()
    for picked in combinations(range(size), rank):
        matrix = [[reduced[r][0][column] for column in picked] for r in range(rank)]
        solution = _solve_square(matrix, [reduced[r][1] for r in range(rank)])
        if solution is None or any(value < 0 for value in solution):
            continue
        point = [Fraction(0)] * size
        for column, value in zip(picked, solution):
            point[column] = value
        vertices.add(tuple(point))
    return tuple(sorted(vertices))


def _pair_hours(first: CandidateResponse, second: CandidateResponse) -> tuple[Fraction, ...]:
    return tuple(
        common_hours(left, right)
        for left, right in zip(first.by_choice, second.by_choice, strict=True)
    )


def pair_matrices(
    first: ValidatedEnvelope, second: ValidatedEnvelope
) -> tuple[tuple[tuple[Fraction, ...], ...], tuple[tuple[Fraction, ...], ...]]:
    """Return the none-repair common-hour matrix and the credit-difference matrix."""
    hours = [
        [_pair_hours(left, right) for right in second.candidates]
        for left in first.candidates
    ]
    none = tuple(tuple(pair[0] for pair in row) for row in hours)
    difference = []
    for row in hours:
        difference.append(tuple(
            (credit.a - credit.b) for credit in (
                compute_pair_credit(*pair) for pair in row
            )
        ))
    return none, tuple(difference)


def _range(values: Sequence[Fraction]) -> ProbabilityRange:
    return ProbabilityRange(min(values), max(values))


def compute_risk(
    first: ValidatedEnvelope,
    second: ValidatedEnvelope,
    mean0: Fraction,
    observed0: Fraction,
    gap: Fraction,
) -> RiskOutcome:
    none, difference = pair_matrices(first, second)
    rows, columns = len(first.candidates), len(second.candidates)
    vertices = joint_vertices(first.masses, second.masses, none, mean0)
    if not vertices:
        return RiskOutcome(STATUS_INCONSISTENT, None, None)

    def mass(pair: tuple[int, int], point: tuple[Fraction, ...]) -> Fraction:
        return point[pair[0] * columns + pair[1]]

    support_masses = []
    conditional_values = []
    favour = {}
    for i in range(rows):
        for j in range(columns):
            favour[(i, j)] = none[i][j] == observed0
    for point in vertices:
        support = sum(
            (mass(pair, point) for pair in favour if favour[pair]), Fraction(0)
        )
        support_masses.append(support)
        if support > 0:
            favourable = sum(
                (mass(pair, point) for pair in favour
                 if favour[pair] and difference[pair[0]][pair[1]] >= gap),
                Fraction(0),
            )
            conditional_values.append(favourable / support)
    support_range = _range(support_masses)
    if support_range.maximum == 0:
        return RiskOutcome(STATUS_UNSUPPORTED, ProbabilityRange(Fraction(0), Fraction(0)), None)
    return RiskOutcome(STATUS_OK, support_range, _range(conditional_values))
