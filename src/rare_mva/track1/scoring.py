"""Public-compatible Track 1 rank and F-max scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from rare_mva.track1.schema import Candidate, Submission, Variant

_RANK_POINTS: Final[tuple[float, ...]] = (
    100.0,
    50.0,
    50.0,
    25.0,
    25.0,
    10.0,
    10.0,
    10.0,
    10.0,
    10.0,
)


@dataclass(frozen=True)
class ScoreResult:
    """The deterministic public-compatible score for one submission."""

    proband_id: str
    rank_points: float
    fmax: float
    f_max_threshold: float | None
    n_predictions_at_f_max: int
    full_match_rank: int | None
    partial_match_rank: int | None
    candidate_count: int

    def to_dict(self) -> dict[str, str | float | int | None]:
        """Return fields in the documented output order."""

        return asdict(self)


def _ranked_candidates(candidates: tuple[Candidate, ...]) -> list[Candidate]:
    """Sort by descending EPCR while preserving input order for ties."""

    return sorted(candidates, key=lambda candidate: -candidate.epcr)


def _candidate_matches(candidate: Candidate, truth: tuple[Variant, ...]) -> bool:
    return tuple(sorted(candidate.variants)) == tuple(sorted(truth))


def _fmax(
    candidates: list[Candidate], truth: tuple[Variant, ...]
) -> tuple[float, float | None, int]:
    truth_set = set(truth)
    thresholds = sorted({candidate.epcr for candidate in candidates}, reverse=True)
    best = 0.0
    best_threshold: float | None = None
    best_row_count = 0
    for threshold in thresholds:
        included = [candidate for candidate in candidates if candidate.epcr >= threshold]
        predicted = {
            variant
            for candidate in included
            for variant in candidate.variants
        }
        true_positives = len(predicted & truth_set)
        precision = true_positives / len(predicted) if predicted else 0.0
        recall = true_positives / len(truth_set)
        if precision + recall:
            f1 = 2.0 * precision * recall / (precision + recall)
            # Match the organizer implementation: retain the first (highest)
            # EPCR threshold when multiple thresholds have the same F score.
            if f1 > best:
                best = f1
                best_threshold = threshold
                best_row_count = len(included)
    return best, best_threshold, best_row_count


def score_submission(submission: Submission, truth: tuple[Variant, ...]) -> ScoreResult:
    """Score a validated submission against one proband's validated truth.

    A full candidate-set match wins once at its best rank. For two-variant truth,
    a best single-variant partial match scores half its rank tier only when no
    full match exists anywhere in the submission.
    """

    if len(truth) not in (1, 2):
        raise ValueError("truth must contain one or two variants")
    for candidate in submission.candidates:
        if len(candidate.variants) not in (1, 2):
            raise ValueError("each candidate must contain one or two variants")
        if len(candidate.variants) == 2 and candidate.variants[0] == candidate.variants[1]:
            raise ValueError("a compound candidate must contain two different variants")

    ranked = _ranked_candidates(submission.candidates)
    full_match_rank: int | None = None
    for rank, candidate in enumerate(ranked, start=1):
        if _candidate_matches(candidate, truth):
            full_match_rank = rank
            break

    partial_match_rank: int | None = None
    rank_points = 0.0
    if full_match_rank is not None:
        rank_points = _RANK_POINTS[full_match_rank - 1]
    elif len(truth) == 2:
        truth_set = set(truth)
        for rank, candidate in enumerate(ranked, start=1):
            if len(set(candidate.variants) & truth_set) == 1:
                partial_match_rank = rank
                rank_points = _RANK_POINTS[rank - 1] / 2.0
                break

    fmax, f_max_threshold, n_predictions_at_f_max = _fmax(ranked, truth)
    return ScoreResult(
        proband_id=submission.proband_id,
        rank_points=rank_points,
        fmax=fmax,
        f_max_threshold=f_max_threshold,
        n_predictions_at_f_max=n_predictions_at_f_max,
        full_match_rank=full_match_rank,
        partial_match_rank=partial_match_rank,
        candidate_count=len(ranked),
    )
